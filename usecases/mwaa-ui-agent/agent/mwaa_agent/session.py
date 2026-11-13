# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""One Strands agent per AgentCore session and translation to bounded UI events."""

from __future__ import annotations

import asyncio
import json
import os
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from strands import Agent, AgentSkills
from strands.models import BedrockModel

from .approval import INTERRUPT_NAME, ApprovalHook
from .context import AgentRequest, SessionContext
from .dag_deploy import ApprovedDeploys
from .prompts import frame_message, system_prompt
from .sanitize import MAX_UI_TEXT_CHARS, clean, redact_values, scrub
from .tools import build_tools, environment_profile

SKILLS_DIR = Path(
    os.environ.get(
        "MWAA_AGENT_SKILLS_DIR", Path(__file__).resolve().parent.parent / "skills"
    )
)
ENABLED_SKILLS = tuple(
    s.strip()
    for s in os.environ.get(
        "MWAA_AGENT_SKILLS", "debugging-mwaa-workflow,testing-mwaa-workflow"
    ).split(",")
    if s.strip()
)
DEFAULT_MODEL_ID = "global.anthropic.claude-sonnet-5-5"


def _profile(context: SessionContext) -> dict:
    """The environment profile must never stop a session from starting."""
    try:
        return environment_profile(context)
    except Exception as err:  # noqa: BLE001
        return {"profile_error": type(err).__name__}


class SessionError(Exception):
    """The request cannot be served in this session."""


class AgentSession:
    def __init__(self, context: SessionContext) -> None:
        self.context = context
        self.lock = asyncio.Lock()
        missing = [
            n for n in ENABLED_SKILLS if not (SKILLS_DIR / n / "SKILL.md").is_file()
        ]
        if missing or not ENABLED_SKILLS:
            # A misspelled MWAA_AGENT_SKILLS entry must not silently drop a skill.
            raise SessionError(
                f"skills not found in {SKILLS_DIR}: {', '.join(missing) or 'none configured'}; "
                "check MWAA_AGENT_SKILLS and build the agent package with scripts/build-agent.sh"
            )
        skill_paths = [str(SKILLS_DIR / name) for name in ENABLED_SKILLS]
        model = BedrockModel(
            model_id=os.environ.get("MODEL_ID", DEFAULT_MODEL_ID),
            region_name=os.environ.get("MODEL_REGION")
            or os.environ.get("AWS_REGION")
            or context.region,
        )
        deploy_approvals = ApprovedDeploys()
        self.agent = Agent(
            model=model,
            system_prompt=system_prompt(context, _profile(context)),
            tools=build_tools(lambda: self.context, SKILLS_DIR, deploy_approvals),
            plugins=[AgentSkills(skills=skill_paths)],
            hooks=[ApprovalHook(lambda: self.context, deploy_approvals)],
            callback_handler=None,
        )
        self._pending: dict[str, dict[str, Any]] = {}

    def bind(self, context: SessionContext) -> None:
        if context.user_id != self.context.user_id:
            raise SessionError("this session belongs to a different user")
        if context.environment_name != self.context.environment_name:
            raise SessionError("this session belongs to a different environment")
        if context.region != self.context.region:
            raise SessionError("this session belongs to a different Region")
        self.context = context

    async def handle(self, request: AgentRequest) -> AsyncIterator[dict[str, Any]]:
        if self.lock.locked():
            yield {
                "type": "error",
                "message": "The agent is still working on the previous request.",
            }
            return
        async with self.lock:
            # Bind under the lock: a rejected concurrent request must not replace the active
            # turn's permissions, Region, or page context.
            self.bind(request.context)
            resuming = request.kind == "approval"
            pending_before = dict(self._pending)
            if request.kind == "message":
                if self._pending:
                    yield {
                        "type": "text",
                        "text": "An earlier action is still waiting for your decision. Approve or decline it first.",
                    }
                    for event in approval_events(list(self._pending.values())):
                        yield event
                    yield {"type": "done", "stop_reason": "interrupt"}
                    return
                agent_input: Any = frame_message(self.context, request.text)
            else:
                missing = set(self._pending) - set(request.decisions)
                unknown = set(request.decisions) - set(self._pending)
                if not self._pending or unknown:
                    yield {
                        "type": "error",
                        "message": "There is no pending action with that id.",
                    }
                    return
                if missing:
                    for event in approval_events([self._pending[i] for i in missing]):
                        yield event
                    yield {"type": "done", "stop_reason": "interrupt"}
                    return
                agent_input = [
                    {
                        "interruptResponse": {
                            "interruptId": i,
                            "response": {"approved": request.decisions[i]},
                        }
                    }
                    for i in self._pending
                ]

            saw_new_approval = False
            completed = False
            try:
                async for event in translate(self.agent.stream_async(agent_input)):
                    if event["type"] == "approval_required":
                        if not saw_new_approval:
                            self._pending = {}
                        self._pending.update({a["id"]: a for a in event["approvals"]})
                        saw_new_approval = True
                    if (
                        event["type"] == "done"
                        and event.get("stop_reason") != "interrupt"
                    ):
                        completed = True
                    yield event
            finally:
                if resuming and completed and not saw_new_approval:
                    self._pending.clear()
                elif resuming and not completed and not saw_new_approval:
                    self._pending = pending_before


# The plugin aborts a turn when one stream event exceeds 128 KiB. JSON escaping can grow a character to six
# bytes (\\uXXXX), so text goes out in chunks of at most 8,000 characters, and each approval card goes out
# as its own event: one 48 KB DAG file fits, three in one event would not.
MAX_TEXT_EVENT_CHARS = 8_000


def text_events(text: str) -> list[dict[str, Any]]:
    """Split text into events the browser appends back together."""
    return [
        {"type": "text", "text": text[i : i + MAX_TEXT_EVENT_CHARS]}
        for i in range(0, len(text), MAX_TEXT_EVENT_CHARS)
    ]


def approval_events(approvals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One event per card; the browser collects them and shows them together when the turn ends."""
    return [{"type": "approval_required", "approvals": [a]} for a in approvals]


MAX_TOOL_DETAIL_CHARS = 2_000
MAX_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 150


def describe_tool_call(name: str, args: Any) -> str:
    """A short, redacted description of one tool call for the expandable line in the chat.

    Display only: arguments are scrubbed by key name (password, token, ...) and by value pattern.
    """
    args = scrub(args) if isinstance(args, dict) else {}
    if name == "airflow_api":
        line = f"{str(args.get('method', 'GET')).upper()} {args.get('path', '')}"
        query = args.get("query")
        if isinstance(query, dict) and query:
            line += "?" + "&".join(f"{k}={v}" for k, v in query.items())
        body = args.get("body")
        detail = line if body in (None, {}) else f"{line}\n{json.dumps(body, indent=1)}"
    elif name == "aws_api":
        detail = f"{args.get('service', '')}:{args.get('operation', '')}"
        if args.get("params"):
            detail += "\n" + json.dumps(args["params"], indent=1, default=str)
    elif name == "deploy_dag":
        # Never the file content here: the approval card shows it in full.
        detail = f"file {args.get('file_name', '')}"
        if args.get("team"):
            detail += f" (team {args['team']})"
        if args.get("overwrite") is True:
            detail += ", replace existing"
    elif name == "read_skill_file":
        detail = f"{args.get('skill_name', '')}/{args.get('path', '')}"
    elif name in ("list_dag_files", "read_dag_file"):
        detail = str(args.get("path") or "DAG folder")
        if args.get("team"):
            detail += f" (team {args['team']})"
    elif name == "lint_dag":
        # Never inline content here: it can be a whole file.
        if args.get("path"):
            detail = f"{args['path']}" + (
                f" (team {args['team']})" if args.get("team") else ""
            )
        else:
            content = args.get("content")
            size = len(content.encode("utf-8")) if isinstance(content, str) else 0
            detail = f"inline file ({size} bytes)"
        if args.get("fix") is True:
            detail += ", with fixes"
    else:
        detail = json.dumps(args, indent=1, default=str)
    return clean(detail, MAX_TOOL_DETAIL_CHARS)


def _tool_error(result: dict[str, Any]) -> str | None:
    """The error code and message of a failed or refused tool call, if the result carries one."""
    for block in result.get("content", []) or []:
        text = block.get("text") if isinstance(block, dict) else None
        if not isinstance(text, str):
            continue
        try:
            data = json.loads(text)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("error"):
            return clean(f"{data.get('error')}: {data.get('message', '')}", 500)
    return None


def extract_suggestions(text: str) -> tuple[str, list[str]]:
    """Split the model's trailing <next_steps> block off the answer and return the validated suggestions.

    Accepted only as one tag that ends the answer, outside any code block. A tag anywhere else is quoted
    content (a task log, DAG source) that an attacker may control, so the text is left as is and no
    suggestion is offered. Linear: no regex backtracking over the answer.
    """
    stripped = text.rstrip()
    open_tag, close_tag = "<next_steps>", "</next_steps>"
    if not stripped.endswith(close_tag):
        return text, []
    start = stripped.rfind(open_tag)
    if start < 0 or stripped.count(open_tag) != 1 or stripped.count(close_tag) != 1:
        return text, []
    before = stripped[:start]
    if before.count("```") % 2:  # inside an unclosed code block
        return text, []
    body = stripped[start + len(open_tag) : -len(close_tag)]
    try:
        items = json.loads(body.strip())
    except ValueError:
        return before.rstrip(), []
    suggestions: list[str] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, str):
            continue
        item = " ".join(item.split())
        if (
            3 <= len(item) <= MAX_SUGGESTION_CHARS
            and redact_values(item) == item
            and "<" not in item  # templates such as <paste> cannot be sent as is
            and not any(
                unicodedata.category(ch) in ("Cf", "Cc", "Co", "Cs") for ch in item
            )
        ):
            suggestions.append(item)
        if len(suggestions) == MAX_SUGGESTIONS:
            break
    return before.rstrip(), suggestions


async def translate(
    stream: AsyncIterator[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Map Strands events to a small, redacted UI-event vocabulary.

    Model text is buffered until a tool boundary or terminal result so a secret split
    across streaming chunks cannot evade the final redaction pass.
    """
    announced: set[str] = set()
    text_buffer = ""

    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            text_buffer += event["data"]
            if len(text_buffer) > MAX_UI_TEXT_CHARS * 2:
                text_buffer = clean(text_buffer, MAX_UI_TEXT_CHARS)
            continue

        # Flush only at real boundaries. Strands interleaves raw stream events ({"event": ...}) between text
        # chunks; flushing on those would redact chunk by chunk and split the <next_steps> block.
        boundary = (
            "current_tool_use" in event or "message" in event or "result" in event
        )
        if text_buffer and boundary:
            text, suggestions = extract_suggestions(text_buffer)
            for chunk in text_events(clean(text, MAX_UI_TEXT_CHARS)):
                yield chunk
            if suggestions:
                yield {"type": "suggestions", "items": suggestions}
            text_buffer = ""

        if "current_tool_use" in event:
            tool_use = event["current_tool_use"] or {}
            tool_id = tool_use.get("toolUseId")
            if tool_id and tool_id not in announced:
                announced.add(tool_id)
                yield {
                    "type": "tool_start",
                    "id": tool_id,
                    "name": clean(str(tool_use.get("name", "")), 100),
                }
        elif "message" in event and isinstance(event["message"], dict):
            message = event["message"]
            if message.get("role") == "assistant":
                for block in message.get("content", []):
                    use = block.get("toolUse") if isinstance(block, dict) else None
                    if use and use.get("toolUseId"):
                        yield {
                            "type": "tool_input",
                            "id": use["toolUseId"],
                            "detail": describe_tool_call(
                                str(use.get("name", "")), use.get("input")
                            ),
                        }
            if message.get("role") == "user":
                for block in message.get("content", []):
                    result = (
                        block.get("toolResult") if isinstance(block, dict) else None
                    )
                    if result:
                        end = {
                            "type": "tool_end",
                            "id": result.get("toolUseId"),
                            "status": result.get("status"),
                        }
                        error = _tool_error(result)
                        if error:
                            end["error"] = error
                        yield end
        elif "result" in event:
            result = event["result"]
            stop_reason = getattr(result, "stop_reason", None)
            if stop_reason == "interrupt":
                # Value-pattern redaction only: the approval hook already refused any request it would
                # change, so cards show exactly what runs, including conf keys such as secret_name.
                approvals = [
                    redact_values(
                        {
                            "id": i.id,
                            **(
                                i.reason
                                if isinstance(i.reason, dict)
                                else {"summary": str(i.reason)}
                            ),
                        }
                    )
                    for i in getattr(result, "interrupts", []) or []
                    if i.name == INTERRUPT_NAME
                ]
                for approval_event in approval_events(approvals):
                    yield approval_event
            yield {"type": "done", "stop_reason": stop_reason}

    if text_buffer:
        text, suggestions = extract_suggestions(text_buffer)
        for chunk in text_events(clean(text, MAX_UI_TEXT_CHARS)):
            yield chunk
        if suggestions:
            yield {"type": "suggestions", "items": suggestions}
