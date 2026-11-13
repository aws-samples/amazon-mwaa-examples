# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""AgentCore Runtime entry point for the MWAA UI agent.

The runtime gives every session its own microVM, so the session table below
normally holds a single entry. The environment this runtime may act on is
pinned by MWAA_ENV_NAME at deploy time; requests for any other environment
are rejected.
"""

from __future__ import annotations

import hmac
import logging
import os
import time
from collections.abc import AsyncIterator
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from botocore.exceptions import ClientError
from mwaa_agent.context import RequestError, parse_request
from mwaa_agent.session import AgentSession, SessionError

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("mwaa_agent")

app = BedrockAgentCoreApp()
SESSIONS: dict[str, tuple[AgentSession, float]] = {}
MAX_PROCESS_SESSIONS = 256
SESSION_IDLE_SECONDS = 3600
PINNED_ENVIRONMENT = os.environ.get("MWAA_ENV_NAME", "")
# The Region drives every AWS client the tools create. AgentCore Runtime sets AWS_REGION to its own Region.
PINNED_REGION = os.environ.get("MWAA_REGION") or os.environ.get("AWS_REGION", "")
LOCAL_INVOCATION_TOKEN = os.environ.get("LOCAL_INVOCATION_TOKEN", "")

# Errors from the model call that mean the runtime's own AWS credentials are the problem.
_CREDENTIAL_ERRORS = {
    "ExpiredTokenException",
    "ExpiredToken",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
    "AccessDeniedException",
}


def _credential_message(code: str) -> str:
    if code.startswith("Expired"):
        problem = "The agent's AWS credentials have expired"
    elif code == "AccessDeniedException":
        problem = "The agent's AWS credentials are not allowed to call the Amazon Bedrock model"
    else:
        problem = "The agent's AWS credentials are not valid"
    if LOCAL_INVOCATION_TOKEN:
        return f"{problem} ({code}). Refresh your AWS credentials and rerun local/start.sh."
    return f"{problem} ({code}). Check the AgentCore Runtime role and its Bedrock permissions."


@app.entrypoint
async def invoke(
    payload: dict[str, Any], context: Any
) -> AsyncIterator[dict[str, Any]]:
    if LOCAL_INVOCATION_TOKEN:
        headers = getattr(context, "request_headers", None) or {}
        supplied = next(
            (
                value
                for key, value in headers.items()
                if key.lower() == "x-mwaa-agent-local-token"
            ),
            "",
        )
        if not hmac.compare_digest(supplied, LOCAL_INVOCATION_TOKEN):
            yield {"type": "error", "message": "not authorized"}
            return
    session_id = getattr(context, "session_id", None)
    if not session_id:
        yield {"type": "error", "message": "missing runtime session id"}
        return
    try:
        request = parse_request(payload)
    except RequestError as err:
        yield {"type": "error", "message": f"invalid request: {err}"}
        return
    if not PINNED_ENVIRONMENT or request.context.environment_name != PINNED_ENVIRONMENT:
        log.warning(
            "rejected request for environment %r", request.context.environment_name
        )
        yield {
            "type": "error",
            "message": "this agent is not configured for this environment",
        }
        return
    if not PINNED_REGION or request.context.region != PINNED_REGION:
        log.warning("rejected request for Region %r", request.context.region)
        yield {
            "type": "error",
            "message": "this agent is not configured for this Region",
        }
        return

    try:
        now = time.monotonic()
        for stale_id, (stale_session, last_used) in list(SESSIONS.items()):
            if (
                last_used < now - SESSION_IDLE_SECONDS
                and not stale_session.lock.locked()
            ):
                SESSIONS.pop(stale_id, None)
        record = SESSIONS.get(session_id)
        if record is None:
            if len(SESSIONS) >= MAX_PROCESS_SESSIONS:
                yield {
                    "type": "error",
                    "message": "The agent has too many active sessions. Try again later.",
                }
                return
            session = AgentSession(request.context)
        else:
            session = record[0]
        SESSIONS[session_id] = (session, now)
        log.info(
            "session=%s user=%s tier=%s kind=%s",
            session_id[:12],
            request.context.user_name,
            request.context.scope.tier,
            request.kind,
        )
        async for event in session.handle(request):
            yield event
        SESSIONS[session_id] = (session, time.monotonic())
    except SessionError as err:
        yield {"type": "error", "message": str(err)}
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "")
        log.exception("agent turn failed: %s", code)
        if code in _CREDENTIAL_ERRORS:
            yield {"type": "error", "message": _credential_message(code)}
        else:
            yield {
                "type": "error",
                "message": "The agent hit an internal error. Check the runtime logs.",
            }
    except Exception:  # pylint: disable=broad-except
        log.exception("agent turn failed")
        yield {
            "type": "error",
            "message": "The agent hit an internal error. Check the runtime logs.",
        }


if __name__ == "__main__":
    # Binds to 127.0.0.1 locally; the SDK only widens the bind inside a container.
    app.run()
