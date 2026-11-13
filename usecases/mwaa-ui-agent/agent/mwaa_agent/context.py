# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Request parsing: the payload contract between the Airflow plugin and the agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .policy import TIER_OPERATE, TIERS, AccessScope

MAX_MESSAGE_CHARS = 20_000
MAX_DAG_IDS = 5_000
MAX_CONTEXT_BYTES = 512 * 1024
MAX_DECISIONS = 20
_DAG_ID = re.compile(r"^[A-Za-z0-9_.\-]{1,250}$")
_INTERRUPT_ID = re.compile(r"^[A-Za-z0-9:_.\-]{1,300}$")


class RequestError(ValueError):
    """The payload does not match the contract."""


@dataclass
class PageContext:
    """Where the user opened the agent from in the Airflow UI."""

    dag_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    map_index: int | None = None

    def describe(self) -> str:
        if not self.dag_id:
            return "The user opened the agent from the Airflow navigation bar (no DAG selected)."
        parts = [f"dag_id={self.dag_id}"]
        if self.run_id:
            parts.append(f"run_id={self.run_id}")
        if self.task_id:
            parts.append(f"task_id={self.task_id}")
        if self.map_index is not None and self.map_index >= 0:
            parts.append(f"map_index={self.map_index}")
        return (
            "The user opened the agent from this Airflow UI page: "
            + ", ".join(parts)
            + "."
        )


@dataclass
class SessionContext:
    """Everything the agent knows about the caller for one request."""

    environment_name: str
    region: str
    airflow_version: str
    user_id: str
    user_name: str
    scope: AccessScope
    page: PageContext = field(default_factory=PageContext)
    dag_deploy_mode: str = "s3_with_approval"


@dataclass
class AgentRequest:
    kind: str  # "message" | "approval"
    context: SessionContext
    text: str = ""
    decisions: dict[str, bool] = field(default_factory=dict)  # interrupt id -> approved


def _str(value, name: str, max_len: int = 256, required: bool = True) -> str | None:
    if value is None or value == "":
        if required:
            raise RequestError(f"'{name}' is required")
        return None
    if (
        not isinstance(value, str)
        or len(value) > max_len
        or "\n" in value
        or "\r" in value
    ):
        raise RequestError(
            f"'{name}' must be a single-line string of at most {max_len} characters"
        )
    return value


# Airflow team names, as Airflow 3.3.1 validates them (airflow/cli/commands/team_command.py).
TEAM_NAME = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")
MAX_TEAMS = 20


def _team_set(values) -> frozenset[str]:
    if values is None:
        return frozenset()
    if not isinstance(values, list) or len(values) > MAX_TEAMS:
        raise RequestError(f"'teams' must be a list of at most {MAX_TEAMS} team names")
    if not all(isinstance(v, str) and TEAM_NAME.match(v) for v in values):
        raise RequestError("'teams' contains an invalid team name")
    return frozenset(values)


def _dag_set(values, name: str) -> frozenset[str]:
    if values is None:
        return frozenset()
    if not isinstance(values, list) or len(values) > MAX_DAG_IDS:
        raise RequestError(f"'{name}' must be a list of at most {MAX_DAG_IDS} DAG ids")
    if not all(isinstance(v, str) and _DAG_ID.match(v) for v in values):
        raise RequestError(f"'{name}' contains an invalid DAG id")
    return frozenset(values)


def parse_request(payload: dict) -> AgentRequest:
    """Validate the plugin payload. Raises RequestError on any contract violation."""
    if not isinstance(payload, dict):
        raise RequestError("payload must be a JSON object")
    ctx = payload.get("context")
    if not isinstance(ctx, dict):
        raise RequestError("'context' is required")
    try:
        context_size = len(json.dumps(ctx, separators=(",", ":")).encode())
    except (TypeError, ValueError) as err:
        raise RequestError("'context' must be JSON serializable") from err
    if context_size > MAX_CONTEXT_BYTES:
        raise RequestError(f"'context' must be at most {MAX_CONTEXT_BYTES} bytes")

    tier = ctx.get("tier")
    if tier not in TIERS:
        raise RequestError(f"'tier' must be one of {TIERS}")
    scope = AccessScope(
        tier=tier,
        all_dags_readable=ctx.get("all_dags_readable") is True,
        readable_dags=_dag_set(ctx.get("readable_dags"), "readable_dags"),
        runnable_dags=_dag_set(ctx.get("runnable_dags"), "runnable_dags"),
        can_deploy_dags=tier == TIER_OPERATE and ctx.get("can_deploy_dags") is True,
        can_edit_task_instances=tier == TIER_OPERATE
        and ctx.get("can_edit_task_instances") is True,
        can_edit_runs=tier == TIER_OPERATE and ctx.get("can_edit_runs") is True,
        dag_lists_truncated=ctx.get("dag_lists_truncated") is True,
        multi_team=ctx.get("multi_team") is True,
        teams=_team_set(ctx.get("teams")),
    )

    page_raw = ctx.get("page") or {}
    if not isinstance(page_raw, dict):
        raise RequestError("'page' must be an object")
    dag_id = _str(page_raw.get("dag_id"), "page.dag_id", 250, required=False)
    if dag_id and not _DAG_ID.match(dag_id):
        raise RequestError("'page.dag_id' is not a valid DAG id")
    map_index = page_raw.get("map_index")
    if map_index is not None and (
        not isinstance(map_index, int) or isinstance(map_index, bool)
    ):
        raise RequestError("'page.map_index' must be an integer")
    page = PageContext(
        dag_id=dag_id,
        run_id=_str(page_raw.get("run_id"), "page.run_id", 250, required=False),
        task_id=_str(page_raw.get("task_id"), "page.task_id", 250, required=False),
        map_index=map_index,
    )

    context = SessionContext(
        environment_name=_str(ctx.get("environment_name"), "environment_name", 80),
        region=_str(ctx.get("region"), "region", 32),
        airflow_version=_str(ctx.get("airflow_version"), "airflow_version", 32),
        user_id=_str(ctx.get("user_id"), "user_id", 256),
        user_name=_str(ctx.get("user_name"), "user_name", 256),
        scope=scope,
        page=page,
        dag_deploy_mode=_str(
            ctx.get("dag_deploy_mode") or "s3_with_approval", "dag_deploy_mode", 32
        ),
    )

    kind = payload.get("type")
    if kind == "message":
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise RequestError("'text' is required for a message")
        if len(text) > MAX_MESSAGE_CHARS:
            raise RequestError(f"'text' must be at most {MAX_MESSAGE_CHARS} characters")
        return AgentRequest(kind=kind, context=context, text=text)
    if kind == "approval":
        decisions = payload.get("decisions")
        if not isinstance(decisions, dict) or not 1 <= len(decisions) <= MAX_DECISIONS:
            raise RequestError(
                f"'decisions' must map 1 to {MAX_DECISIONS} interrupt ids to true or false"
            )
        for interrupt_id, approved in decisions.items():
            if not _INTERRUPT_ID.match(interrupt_id):
                raise RequestError("'decisions' contains an invalid interrupt id")
            if not isinstance(approved, bool):
                raise RequestError("each decision must be true or false")
        return AgentRequest(kind=kind, context=context, decisions=dict(decisions))
    raise RequestError("'type' must be 'message' or 'approval'")
