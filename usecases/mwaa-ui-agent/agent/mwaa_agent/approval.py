# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Human-in-the-loop gate: state-changing tool calls pause the agent until the user approves them."""

from __future__ import annotations

import re
from typing import Any

from strands.hooks import BeforeToolCallEvent, HookProvider, HookRegistry

from . import policy
from .dag_deploy import DEFAULT_APPROVALS, ApprovedDeploys, DagDeployError
from .sanitize import redact_values
from .tools import ContextGetter, check_dag_deploy, deploy_target

INTERRUPT_NAME = "mwaa-agent-approval"

# Keys that name a credential outright (password, api_key, db_token), as opposed to keys that only mention
# one (secret_name, max_tokens, credentials_path). A value under such a key would sit in plain text on the
# approval card and in the browser's session storage, so the mutation is refused instead.
# Matched against the key lower-cased with separators removed, so db_password, db-password, dbPassword and
# sessionToken all end in a credential word, while secret_name or max_tokens do not.
_CREDENTIAL_SUFFIX = re.compile(
    r"(?:password|passwd|pwd|secret|token|apikey|accesskey|secretkey|privatekey|clientsecret)$"
)


def _is_credential_key(key: object) -> bool:
    return bool(_CREDENTIAL_SUFFIX.search(re.sub(r"[^a-z0-9]", "", str(key).lower())))


def _credential_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            (_is_credential_key(k) and v not in (None, "", False))
            or _credential_value(v)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(_credential_value(v) for v in value)
    return False


DECLINED_MESSAGE = (
    "The user declined this action. Do not retry it or try an equivalent call; "
    "explain what you would have done and ask how they want to proceed."
)


class ApprovalHook(HookProvider):
    """Ask the user before any tool call the policy marks as needing approval."""

    def __init__(
        self,
        get_context: ContextGetter,
        deploy_approvals: ApprovedDeploys | None = None,
    ) -> None:
        self._get_context = get_context
        self._deploys = deploy_approvals or DEFAULT_APPROVALS

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._gate)

    def _gate(self, event: BeforeToolCallEvent) -> None:
        tool_use = event.tool_use
        if tool_use.get("name") == "deploy_dag":
            self._gate_deploy(event)
            return
        if tool_use.get("name") != "airflow_api":
            return
        args = tool_use.get("input") or {}
        method = str(args.get("method", "GET")).upper()
        if method == "GET":
            return
        path = str(args.get("path", ""))
        body = args.get("body") if isinstance(args.get("body"), dict) else None

        query = args.get("query") if isinstance(args.get("query"), dict) else None
        decision = policy.check_airflow(
            self._get_context().scope, method, path, body, query
        )
        if not decision.allowed:
            # Do not ask for approval of something the policy will refuse anyway.
            event.cancel_tool = f"Blocked by agent policy: {decision.reason}"
            return
        if not decision.needs_approval:
            return

        # The card is redacted before it reaches the browser (session.translate, with redact_values).
        # Refuse anything that redaction would change, so what the user approves is exactly what runs, as
        # deploy_dag does. Key names alone (secret_name, max_tokens) do not count: they are shown as is.
        request = {"path": path, "query": query, "body": body}
        if redact_values(request) != request or _credential_value(request):
            event.cancel_tool = (
                "Blocked by agent policy: this request contains credential-shaped keys or values that "
                "the approval card would hide, so the user could not see what they approve. Do not "
                "retry with the value disguised; ask the user to make this change in the Airflow UI."
            )
            return

        answer = event.interrupt(
            INTERRUPT_NAME,
            reason={
                "tool": "airflow_api",
                "summary": policy.describe_mutation(method, path),
                "method": method,
                "path": path,
                "query": query,
                "body": body,
            },
        )
        if not (isinstance(answer, dict) and answer.get("approved") is True):
            event.cancel_tool = DECLINED_MESSAGE

    def _gate_deploy(self, event: BeforeToolCallEvent) -> None:
        """Validate first, then show the user exactly what will be written and where."""
        args = event.tool_use.get("input") or {}
        tool_use_id = str(event.tool_use.get("toolUseId", ""))
        file_name, content = args.get("file_name"), args.get("content")
        overwrite = args.get("overwrite") is True
        ctx = self._get_context()
        try:
            dag, team = check_dag_deploy(ctx, file_name, content, args.get("team"))
            target = deploy_target(ctx, team)
            where = target.describe(dag.file_name)
            current = target.state(dag.file_name)
        except DagDeployError as err:
            event.cancel_tool = f"Blocked by agent policy: {err}"
            return
        except Exception as err:  # noqa: BLE001 - never ask for approval when the target is unknown
            event.cancel_tool = f"Could not check the DAG folder: {type(err).__name__}"
            return
        # The state the card shows. On resume the hook runs again; this returns what was shown the first time.
        shown = self._deploys.shown(tool_use_id, dag, current, where)
        exists = shown is not None
        if exists and not overwrite:
            self._deploys.forget(tool_use_id)
            event.cancel_tool = (
                f"Blocked by agent policy: {dag.file_name} already exists. Read it first, and only call again "
                "with overwrite=true if the user asked to replace it."
            )
            return
        answer = event.interrupt(
            INTERRUPT_NAME,
            reason={
                "tool": "deploy_dag",
                "summary": f"{'replace' if exists else 'add'} the DAG file {dag.file_name}",
                "file_name": dag.file_name,
                "target": where,
                "team": team,
                "replaces_existing": exists,
                "bytes": len(dag.data),
                "sha256": dag.sha256_hex,
                "content": dag.content,
            },
        )
        if not (isinstance(answer, dict) and answer.get("approved") is True):
            self._deploys.forget(tool_use_id)
            event.cancel_tool = DECLINED_MESSAGE
            return
        if current != shown:
            self._deploys.forget(tool_use_id)
            event.cancel_tool = (
                f"Blocked by agent policy: {dag.file_name} changed after the approval card was shown, so "
                "nothing was written. Read the DAG folder again and ask the user to approve a new upload."
            )
            return
        self._deploys.approve(tool_use_id)
