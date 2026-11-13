# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Invoke AgentCore Runtime and relay a bounded event stream as NDJSON."""

from __future__ import annotations

import http.client
import json
import logging
import socket
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator

import boto3
from urllib3 import exceptions as urllib3_exceptions
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, UnknownServiceError

from mwaa_agent_ui.config import Settings

log = logging.getLogger(__name__)
SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
MAX_STREAM_BYTES = 2 * 1024 * 1024
MAX_EVENT_BYTES = 128 * 1024
MAX_STREAM_EVENTS = 10_000
_client_cache: dict[tuple[str, int], object] = {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the runtime session header to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_LOCAL_OPENER = urllib.request.build_opener(_NoRedirect)


def _error_line(message: str) -> bytes:
    return json.dumps({"type": "error", "message": message}).encode() + b"\n"


def _raw_lines(raw) -> Iterator[bytes]:
    """Lines from a urllib3 response as soon as they arrive.

    read1() returns whatever bytes have arrived (no waiting for a full buffer, unlike
    StreamingBody.iter_lines), and reading 64 KiB at a time avoids readline()'s one-byte reads. A line
    longer than MAX_EVENT_BYTES is passed on as one oversized piece, which _sse_to_ndjson rejects.
    urllib3 errors are translated into the errors stream_invoke already reports.
    """
    pending = b""
    try:
        while True:
            chunk = raw.read1(65536)
            if not chunk:
                break
            pending += chunk
            *complete, pending = pending.split(b"\n")
            for line in complete:
                yield line + b"\n"
            if len(pending) > MAX_EVENT_BYTES:
                yield pending
                return
    except urllib3_exceptions.HTTPError as err:
        raise OSError(f"agent stream failed: {type(err).__name__}") from err
    if pending:
        yield pending


def _sse_to_ndjson(lines: Iterator[bytes]) -> Iterator[bytes]:
    total = 0
    events = 0
    for raw in lines:
        total += len(raw)
        if (
            len(raw) > MAX_EVENT_BYTES
            or total > MAX_STREAM_BYTES
            or events >= MAX_STREAM_EVENTS
        ):
            yield _error_line(
                "The agent response exceeded its safety limit. Narrow the request and try again."
            )
            return
        line = raw.strip()
        if not line.startswith(b"data:"):
            continue
        data = line[5:].strip()
        try:
            event = json.loads(data)
        except ValueError:
            continue
        if isinstance(event, dict) and "error" in event and "type" not in event:
            log.error("agent stream returned an internal error")
            event = {
                "type": "error",
                "message": "The agent hit an internal error. Check the runtime logs.",
            }
        if isinstance(event, dict):
            events += 1
            yield json.dumps(event).encode() + b"\n"


def _agentcore_client(settings: Settings):
    key = (settings.region, settings.read_timeout_seconds)
    if key not in _client_cache:
        _client_cache[key] = boto3.client(
            "bedrock-agentcore",
            region_name=settings.region,
            config=Config(
                connect_timeout=10,
                read_timeout=settings.read_timeout_seconds,
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )
    return _client_cache[key]


def _interrupter(raw) -> Callable[[], None]:
    """A function that makes a read blocked on ``raw`` (in another thread) return promptly.

    Closing the response would not do it: close() waits for the buffered reader's lock, which the blocked
    read holds, so it would block the caller (the api-server's event loop) until the next upstream event.
    Shutting the socket down does not take that lock and wakes the read at once.
    """

    def interrupt() -> None:
        if hasattr(raw, "shutdown"):  # urllib3 2.3+ (botocore's raw stream)
            try:
                raw.shutdown()
                return
            except (ValueError, RuntimeError, OSError):
                pass
        # http.client.HTTPResponse: the local transport's response, or urllib3 < 2.3's _fp.
        resp = (
            raw
            if isinstance(raw, http.client.HTTPResponse)
            else getattr(raw, "_fp", None)
        )
        sock = getattr(getattr(getattr(resp, "fp", None), "raw", None), "_sock", None)
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    return interrupt


def stream_invoke(
    settings: Settings,
    session_id: str,
    payload: dict,
    on_open: Callable[[Callable[[], None]], None] | None = None,
) -> Iterator[bytes]:
    """Yield NDJSON event lines from one turn. Transport failures become generic events.

    ``on_open`` receives a function that interrupts the upstream response at the socket level; calling it
    from another thread makes a blocked read return promptly, so the turn's thread ends when the browser
    goes away. It never blocks.
    """
    body = json.dumps(payload).encode()
    try:
        if settings.local_agent_url:
            request = urllib.request.Request(
                settings.local_agent_url.rstrip("/") + "/invocations",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                    SESSION_HEADER: session_id,
                    "X-MWAA-Agent-Local-Token": settings.local_agent_token,
                },
                method="POST",
            )
            with _LOCAL_OPENER.open(
                request, timeout=settings.read_timeout_seconds
            ) as response:  # nosec B310
                if on_open:
                    on_open(_interrupter(response))
                yield from _sse_to_ndjson(
                    iter(lambda: response.readline(MAX_EVENT_BYTES + 1), b"")
                )
            return

        response = _agentcore_client(settings).invoke_agent_runtime(
            agentRuntimeArn=settings.runtime_arn,
            runtimeSessionId=session_id,
            payload=body,
            contentType="application/json",
            accept="text/event-stream",
        )
        stream = response["response"]
        if on_open:
            on_open(_interrupter(getattr(stream, "_raw_stream", stream)))
        try:
            if "text/event-stream" in response.get("contentType", ""):
                # Line by line from the raw stream, like the local transport. StreamingBody.iter_lines()
                # reads 1 KiB chunks and blocks until a whole chunk arrives, which held small events such as
                # tool_start back until more output came.
                raw = getattr(stream, "_raw_stream", None)
                lines = (
                    _raw_lines(raw)
                    if raw is not None and hasattr(raw, "read1")
                    else stream.iter_lines(keepends=True)
                )
                yield from _sse_to_ndjson(lines)
            else:
                yield from _sse_to_ndjson(
                    iter([b"data: " + stream.read(MAX_STREAM_BYTES + 1)])
                )
        finally:
            stream.close()
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "ClientError")
        log.warning("InvokeAgentRuntime failed: %s", code)
        if code == "AccessDeniedException":
            yield _error_line(
                "The environment's execution role is not allowed to invoke the agent runtime."
            )
        else:
            yield _error_line(f"Could not reach the agent ({code}).")
    except UnknownServiceError:
        yield _error_line(
            "This environment's boto3 is too old for Amazon Bedrock AgentCore; use Airflow 3.1 or later."
        )
    except (
        BotoCoreError,
        OSError,
        ValueError,
        http.client.HTTPException,
        urllib.error.URLError,
    ) as err:
        log.warning("agent invocation failed: %s", type(err).__name__)
        yield _error_line("Could not reach the agent. Try again in a moment.")
