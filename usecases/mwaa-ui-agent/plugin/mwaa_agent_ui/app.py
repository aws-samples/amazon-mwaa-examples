# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""FastAPI app mounted by the plugin under /mwaa-agent.

Airflow mounts plugin apps without any authentication, so every route here
requires a signed-in Airflow user (the same JWT the Airflow UI uses), and the
agent's permissions are derived from that user's Airflow permissions on each
request.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Annotated

import anyio
from airflow import __version__ as airflow_version
from airflow.api_fastapi.auth.managers.models.base_user import BaseUser
from airflow.api_fastapi.core_api.security import get_user
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

# Absolute imports: Airflow's plugin manager also imports each file in the plugins folder on its own,
# where relative imports fail with "attempted relative import with no known parent package".
from mwaa_agent_ui.access import UserAccess, resolve_access
from mwaa_agent_ui.config import ConfigError, Settings, load_settings
from mwaa_agent_ui.runtime_client import stream_invoke

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "app.js": "text/javascript",
    "styles.css": "text/css",
    "launcher.js": "text/javascript",
}
CSRF_HEADER = "x-mwaa-agent"
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
_SESSION_ID = r"^[A-Za-z0-9-]{16,100}$"
_INTERRUPT_ID = re.compile(r"^[A-Za-z0-9:_.-]{1,300}$")
_DAG_ID = re.compile(r"^[A-Za-z0-9_.-]{1,250}$")
_ENTITY_ID = r"^[A-Za-z0-9_.:+@~-]{1,250}$"
MAX_GLOBAL_INVOCATIONS = 8
MAX_USER_INVOCATIONS = 2
MAX_USER_INVOCATIONS_PER_MINUTE = 20
# Per DAG list sent to the agent; two lists stay well under the agent's 512 KiB context limit.
MAX_CONTEXT_DAG_IDS = 5_000
MAX_CONTEXT_DAG_LIST_BYTES = 200 * 1024


class PageContext(BaseModel):
    dag_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.-]{1,250}$")
    run_id: str | None = Field(default=None, pattern=_ENTITY_ID)
    task_id: str | None = Field(default=None, pattern=_ENTITY_ID)
    map_index: int | None = Field(default=None, ge=-1, le=2_147_483_647)


class ChatRequest(BaseModel):
    session_id: str = Field(pattern=_SESSION_ID)
    message: str = Field(min_length=1, max_length=20_000)
    page: PageContext = Field(default_factory=PageContext)


class ApprovalRequest(BaseModel):
    session_id: str = Field(pattern=_SESSION_ID)
    # One decision per pending action: interrupt id -> approved.
    decisions: dict[str, bool] = Field(min_length=1, max_length=20)
    page: PageContext = Field(default_factory=PageContext)


def require_access(user: Annotated[BaseUser, Depends(get_user)]) -> UserAccess:
    access = resolve_access(user)
    if not access.readable_dags and not access.all_dags_readable:
        raise HTTPException(
            status_code=403,
            detail="You need read access to at least one DAG to use the agent.",
        )
    return access


def require_settings() -> Settings:
    try:
        return load_settings()
    except ConfigError as err:
        log.error("MWAA agent plugin is not configured: %s", err)
        raise HTTPException(
            status_code=503, detail=f"The agent is not configured: {err}"
        ) from err


def require_json_and_csrf_header(request: Request) -> None:
    """Reject cross-site form posts: browsers cannot send this header cross-origin without a CORS preflight."""
    if request.headers.get(CSRF_HEADER) != "1":
        raise HTTPException(status_code=403, detail="Missing request header.")
    if not request.headers.get("content-type", "").startswith("application/json"):
        raise HTTPException(
            status_code=415, detail="Content-Type must be application/json."
        )


AccessDep = Annotated[UserAccess, Depends(require_access)]
SettingsDep = Annotated[Settings, Depends(require_settings)]

# Router-level dependency: no route in this app is reachable without a valid Airflow login.
app = FastAPI(
    title="MWAA UI Agent",
    dependencies=[Depends(get_user)],
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


def runtime_session_id(
    access: UserAccess, settings: Settings, client_session_id: str
) -> str:
    """Namespace the browser's session id by user and environment, so users cannot reach each other's sessions."""
    digest = hashlib.sha256(
        f"{access.user_id}\x00{settings.environment_name}\x00{client_session_id}".encode()
    ).hexdigest()
    return f"airflow-{digest}"


def storage_owner_id(access: UserAccess, settings: Settings | None) -> str:
    """Opaque browser-storage owner binding; contains no raw user identifier."""
    environment = settings.environment_name if settings else "unconfigured"
    return hashlib.sha256(f"{access.user_id}\x00{environment}".encode()).hexdigest()


def _bounded_dag_list(
    dag_ids: frozenset[str], first: str | None
) -> tuple[list[str], bool]:
    """The DAG ids to send, within the agent's per-list limits, and whether any were left out.

    The agent rejects a context over 512 KiB or a list over 5,000 ids. A user with many individual DAG grants
    (rather than access to all DAGs) would otherwise get "invalid request" on every turn. The DAG on the
    current page goes first, so the user can always reach it by opening its page.
    """
    ordered = sorted(dag_ids)
    if first in dag_ids:
        ordered.remove(first)
        ordered.insert(0, first)
    kept: list[str] = []
    size = 0
    for dag_id in ordered:
        size += len(dag_id) + 3  # quotes and comma in the JSON list
        if len(kept) >= MAX_CONTEXT_DAG_IDS or size > MAX_CONTEXT_DAG_LIST_BYTES:
            return kept, True
        kept.append(dag_id)
    return kept, False


def agent_context(access: UserAccess, settings: Settings, page: PageContext) -> dict:
    # Only pass hierarchical page context for a DAG the user can see.
    if not page.dag_id or not access.can_read(page.dag_id):
        page = PageContext()
    elif not page.run_id:
        page = PageContext(dag_id=page.dag_id)
    elif not page.task_id:
        page = PageContext(dag_id=page.dag_id, run_id=page.run_id)
    readable, readable_cut = (
        ([], False)
        if access.all_dags_readable
        else _bounded_dag_list(access.readable_dags, page.dag_id)
    )
    runnable, runnable_cut = _bounded_dag_list(access.runnable_dags, page.dag_id)
    return {
        "environment_name": settings.environment_name,
        "region": settings.region,
        "airflow_version": airflow_version,
        "user_id": access.user_id,
        "user_name": access.user_name,
        "tier": access.tier,
        "all_dags_readable": access.all_dags_readable,
        "readable_dags": readable,
        "runnable_dags": runnable,
        "dag_lists_truncated": readable_cut or runnable_cut,
        "can_deploy_dags": access.can_deploy_dags,
        "can_edit_task_instances": access.can_edit_task_instances,
        "can_edit_runs": access.can_edit_runs,
        "multi_team": access.multi_team,
        "teams": sorted(access.teams)[:20],
        "page": page.model_dump(),
        "dag_deploy_mode": settings.dag_deploy_mode,
    }


class InvocationLimiter:
    """Small in-process abuse guard; service quotas remain the second layer."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global_active = 0
        self._active: dict[str, int] = defaultdict(int)
        self._recent: dict[str, deque[float]] = defaultdict(deque)

    def acquire(self, user_id: str) -> None:
        now = time.monotonic()
        with self._lock:
            recent = self._recent[user_id]
            while recent and recent[0] < now - 60:
                recent.popleft()
            if len(recent) >= MAX_USER_INVOCATIONS_PER_MINUTE:
                raise HTTPException(
                    status_code=429,
                    detail="Too many agent requests. Try again in a minute.",
                )
            if (
                self._active[user_id] >= MAX_USER_INVOCATIONS
                or self._global_active >= MAX_GLOBAL_INVOCATIONS
            ):
                raise HTTPException(
                    status_code=429,
                    detail="Too many agent requests are already running. Try again shortly.",
                )
            recent.append(now)
            self._active[user_id] += 1
            self._global_active += 1

    def release(self, user_id: str) -> None:
        with self._lock:
            self._active[user_id] = max(0, self._active[user_id] - 1)
            self._global_active = max(0, self._global_active - 1)
            if not self._active[user_id] and not self._recent[user_id]:
                self._active.pop(user_id, None)
                self._recent.pop(user_id, None)


_LIMITER = InvocationLimiter()


def _stream(
    settings: Settings, session_id: str, payload: dict, user_id: str
) -> StreamingResponse:
    _LIMITER.acquire(user_id)
    stop = threading.Event()
    lock = threading.Lock()
    state = {"in_flight": False, "released": False, "close": None}

    def release_once() -> None:
        with lock:
            if state["released"]:
                return
            state["released"] = True
        _LIMITER.release(user_id)

    def on_open(close) -> None:
        with lock:
            state["close"] = close
        if stop.is_set():
            close()  # the browser left before the response opened

    upstream = stream_invoke(settings, session_id, payload, on_open=on_open)

    def next_chunk() -> bytes | None:
        # Marked in flight here, in the worker thread, not before run_sync: a cancel can land before the
        # thread starts, and then this function never runs and the async side must release the slot.
        with lock:
            state["in_flight"] = True
        try:
            return None if stop.is_set() else next(upstream, None)
        finally:
            with lock:
                state["in_flight"] = False
            if stop.is_set():
                release_once()  # the browser left while this read was blocked

    async def limited_stream():
        # The upstream read blocks in a worker thread. abandon_on_cancel lets a browser disconnect cancel
        # this generator at once; the finally block then interrupts the upstream socket (a non-blocking
        # shutdown, safe on the event loop), which makes the blocked read return, so the thread and the
        # AgentCore stream end promptly. The slot is released only once no read is in flight, so the
        # limiter keeps bounding running turns.
        try:
            while True:
                chunk = await anyio.to_thread.run_sync(
                    next_chunk, abandon_on_cancel=True
                )
                if chunk is None:
                    break
                yield chunk
        finally:
            stop.set()
            with lock:
                close, in_flight = state["close"], state["in_flight"]
            if close is not None:
                try:
                    close()
                except Exception:  # noqa: BLE001 - interrupting a broken stream must not mask the disconnect
                    log.debug("interrupting the upstream stream failed", exc_info=True)
            if not in_flight:
                release_once()

    return StreamingResponse(
        limited_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/")
def index() -> Response:
    return FileResponse(
        STATIC_DIR / "index.html", media_type="text/html", headers=SECURITY_HEADERS
    )


@app.get("/static/{name}")
def static(name: str) -> Response:
    if name not in STATIC_FILES:
        raise HTTPException(status_code=404)
    return FileResponse(
        STATIC_DIR / name, media_type=STATIC_FILES[name], headers=SECURITY_HEADERS
    )


@app.get("/api/me")
def me(access: AccessDep) -> JSONResponse:
    try:
        settings = load_settings()
        config_error = None
    except ConfigError as err:
        settings, config_error = None, str(err)
    return JSONResponse(
        {
            "user_name": access.user_name,
            "tier": access.tier,
            "environment_name": settings.environment_name if settings else None,
            # Lets the UI label a local runner clearly, so it is not mistaken for Amazon MWAA.
            "deployment": (
                None
                if not settings
                else "local"
                if settings.local_agent_url
                else "mwaa"
            ),
            "airflow_version": airflow_version,
            "runnable_dag_count": len(access.runnable_dags),
            "can_deploy_dags": access.can_deploy_dags,
            "storage_owner_id": storage_owner_id(access, settings),
            "config_error": config_error,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/api/chat", dependencies=[Depends(require_json_and_csrf_header)])
def chat(
    body: ChatRequest, access: AccessDep, settings: SettingsDep
) -> StreamingResponse:
    payload = {
        "type": "message",
        "text": body.message,
        "context": agent_context(access, settings, body.page),
    }
    return _stream(
        settings,
        runtime_session_id(access, settings, body.session_id),
        payload,
        access.user_id,
    )


@app.post("/api/approve", dependencies=[Depends(require_json_and_csrf_header)])
def approve(
    body: ApprovalRequest, access: AccessDep, settings: SettingsDep
) -> StreamingResponse:
    if any(not _INTERRUPT_ID.fullmatch(k) for k in body.decisions):
        raise HTTPException(status_code=422, detail="Invalid interrupt id.")
    for interrupt_id, approved in body.decisions.items():
        # %r escapes control characters even though validation already excludes them.
        log.info(
            "user=%r decision=%s interrupt=%r",
            access.user_name,
            "approved" if approved else "declined",
            interrupt_id,
        )
    payload = {
        "type": "approval",
        "decisions": body.decisions,
        "context": agent_context(access, settings, body.page),
    }
    return _stream(
        settings,
        runtime_session_id(access, settings, body.session_id),
        payload,
        access.user_id,
    )
