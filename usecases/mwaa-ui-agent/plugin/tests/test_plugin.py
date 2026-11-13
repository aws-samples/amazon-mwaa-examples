# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import contextlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from mwaa_agent_ui import access as access_mod
from mwaa_agent_ui import app as app_mod
from mwaa_agent_ui.access import UserAccess
from mwaa_agent_ui.config import ConfigError, load_settings

ARN = "arn:aws:bedrock-agentcore:eu-west-1:123456789012:runtime/mwaa_ui_agent-abc123"
SESSION = "0123456789abcdef-0123"
HEADERS = {"X-MWAA-Agent": "1", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def settings_env(monkeypatch):
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__RUNTIME_ARN", ARN)
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__ENVIRONMENT_NAME", "env1")
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__REGION", "eu-west-1")


def make_access(
    name="alice", tier="operate", readable=("etl",), runnable=("etl",), all_dags=False
):
    return UserAccess(
        user_id=name,
        user_name=name,
        tier=tier,
        all_dags_readable=all_dags,
        readable_dags=frozenset(readable),
        runnable_dags=frozenset(runnable),
    )


@pytest.fixture
def client(monkeypatch):
    calls = []

    def fake_stream(settings, session_id, payload, on_open=None):
        calls.append({"session_id": session_id, "payload": payload})
        yield json.dumps({"type": "text", "text": "hi"}).encode() + b"\n"

    current = {"access": make_access()}
    monkeypatch.setattr(app_mod, "stream_invoke", fake_stream)
    monkeypatch.setattr(app_mod, "resolve_access", lambda user: current["access"])
    app_mod.app.dependency_overrides[app_mod.get_user] = lambda: SimpleNamespace(
        get_id=lambda: "x", get_name=lambda: "x"
    )
    yield TestClient(app_mod.app), calls, current
    app_mod.app.dependency_overrides.clear()


def test_every_route_requires_login():
    anonymous = TestClient(app_mod.app)
    for method, path in [
        ("get", "/"),
        ("get", "/static/app.js"),
        ("get", "/static/launcher.js"),
        ("get", "/api/me"),
        ("post", "/api/chat"),
        ("post", "/api/approve"),
    ]:
        kwargs = {"json": {}} if method == "post" else {}
        response = getattr(anonymous, method)(path, headers=HEADERS, **kwargs)
        assert response.status_code == 401, path


def test_index_has_security_headers(client):
    c, _, _ = client
    response = c.get("/")
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert c.get("/static/../app.py").status_code == 404
    assert c.get("/static/other.js").status_code == 404


def test_me(client):
    c, _, _ = client
    body = c.get("/api/me").json()
    assert body == {
        "user_name": "alice",
        "tier": "operate",
        "environment_name": "env1",
        "deployment": "mwaa",
        "airflow_version": body["airflow_version"],
        "runnable_dag_count": 1,
        "can_deploy_dags": False,
        "storage_owner_id": body["storage_owner_id"],
        "config_error": None,
    }
    assert (
        len(body["storage_owner_id"]) == 64 and "alice" not in body["storage_owner_id"]
    )


def test_me_labels_local_runner(client, monkeypatch):
    c, _, _ = client
    monkeypatch.delenv("AIRFLOW__MWAA_AGENT__RUNTIME_ARN", raising=False)
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_URL", "http://mwaa-agent:8080")
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_TOKEN", "t" * 32)
    assert c.get("/api/me").json()["deployment"] == "local"


def test_csrf_header_and_json_required(client):
    c, calls, _ = client
    body = {"session_id": SESSION, "message": "hi"}
    assert (
        c.post(
            "/api/chat", json=body, headers={"Content-Type": "application/json"}
        ).status_code
        == 403
    )
    assert (
        c.post(
            "/api/chat",
            content="session_id=x",
            headers={
                "X-MWAA-Agent": "1",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ).status_code
        == 415
    )
    assert not calls


def test_chat_forwards_scoped_context(client):
    c, calls, _ = client
    response = c.post(
        "/api/chat",
        headers=HEADERS,
        json={
            "session_id": SESSION,
            "message": "why?",
            "page": {"dag_id": "etl", "run_id": "r1"},
        },
    )
    assert (
        response.status_code == 200
        and json.loads(response.text.splitlines()[0])["type"] == "text"
    )
    ctx = calls[0]["payload"]["context"]
    assert (
        ctx["tier"] == "operate"
        and ctx["readable_dags"] == ["etl"]
        and ctx["page"]["dag_id"] == "etl"
    )
    assert ctx["can_edit_task_instances"] is False and ctx["can_edit_runs"] is False
    assert (
        calls[0]["session_id"].startswith("airflow-")
        and SESSION not in calls[0]["session_id"]
    )


def test_page_context_dropped_for_unreadable_dag(client):
    c, calls, _ = client
    c.post(
        "/api/chat",
        headers=HEADERS,
        json={"session_id": SESSION, "message": "x", "page": {"dag_id": "secret_dag"}},
    )
    assert calls[0]["payload"]["context"]["page"]["dag_id"] is None


def test_sessions_are_namespaced_per_user(client):
    c, calls, current = client
    body = {"session_id": SESSION, "message": "x"}
    c.post("/api/chat", headers=HEADERS, json=body)
    current["access"] = make_access(name="mallory")
    c.post("/api/chat", headers=HEADERS, json=body)
    assert calls[0]["session_id"] != calls[1]["session_id"]


def test_user_without_dag_access_is_rejected(client):
    c, calls, current = client
    current["access"] = make_access(tier="read", readable=(), runnable=())
    assert (
        c.post(
            "/api/chat", headers=HEADERS, json={"session_id": SESSION, "message": "x"}
        ).status_code
        == 403
    )
    assert not calls


def test_invalid_session_id_rejected(client):
    c, calls, _ = client
    assert (
        c.post(
            "/api/chat", headers=HEADERS, json={"session_id": "short", "message": "x"}
        ).status_code
        == 422
    )
    assert not calls


def test_approve_forwards_all_decisions(client):
    c, calls, _ = client
    c.post(
        "/api/approve",
        headers=HEADERS,
        json={"session_id": SESSION, "decisions": {"i1": False, "i2": True}},
    )
    assert calls[0]["payload"]["type"] == "approval"
    assert calls[0]["payload"]["decisions"] == {"i1": False, "i2": True}
    assert (
        c.post(
            "/api/approve",
            headers=HEADERS,
            json={"session_id": SESSION, "decisions": {}},
        ).status_code
        == 422
    )
    assert len(calls) == 1


def test_unconfigured_plugin_returns_503(client, monkeypatch):
    c, calls, _ = client
    monkeypatch.delenv("AIRFLOW__MWAA_AGENT__RUNTIME_ARN")
    assert (
        c.post(
            "/api/chat", headers=HEADERS, json={"session_id": SESSION, "message": "x"}
        ).status_code
        == 503
    )
    assert "runtime_arn" in c.get("/api/me").json()["config_error"]
    assert not calls


@pytest.mark.parametrize(
    "key,value",
    [
        ("RUNTIME_ARN", "arn:aws:iam::123456789012:role/x"),
        ("LOCAL_AGENT_URL", "http://10.0.0.5:8080"),
        ("LOCAL_AGENT_URL", "https://localhost:8080"),
        ("LOCAL_AGENT_URL", "http://agent.example.com:8080"),
        ("DAG_DEPLOY_MODE", "yolo"),
        ("READ_TIMEOUT_SECONDS", "0"),
        ("READ_TIMEOUT_SECONDS", "901"),
        ("LOCAL_AGENT_URL", "http://mwaa-agent:notaport"),
        ("LOCAL_AGENT_URL", "http://user:pass@mwaa-agent:8080"),
        ("LOCAL_AGENT_URL", "http://mwaa-agent:8080/path"),
    ],
)
def test_config_validation(monkeypatch, key, value):
    monkeypatch.setenv(f"AIRFLOW__MWAA_AGENT__{key}", value)
    with pytest.raises(ConfigError):
        load_settings()


def test_local_agent_url_allowed_on_loopback(monkeypatch):
    monkeypatch.delenv("AIRFLOW__MWAA_AGENT__RUNTIME_ARN")
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_TOKEN", "a" * 32)
    assert load_settings().local_agent_url == "http://127.0.0.1:8080"
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_URL", "http://mwaa-agent:8080")
    assert load_settings().local_agent_url == "http://mwaa-agent:8080"


class FakeAuthManager:
    def __init__(
        self,
        readable,
        editable,
        can_create_runs,
        global_read=False,
        can_edit_connections=False,
        entity_rights=None,
    ):
        self.readable, self.editable, self.can_create_runs, self.global_read = (
            readable,
            editable,
            can_create_runs,
            global_read,
        )
        self.can_edit_connections = can_edit_connections
        # (method, access_entity) -> bool for task-instance and DAG-run checks; defaults to can_create_runs.
        self.entity_rights = entity_rights or {}

    def get_authorized_dag_ids(self, user, method="GET"):
        return set(self.readable if method == "GET" else self.editable)

    def is_authorized_dag(self, method, user, access_entity=None, details=None):
        if (method, access_entity) in self.entity_rights:
            return self.entity_rights[(method, access_entity)]
        return self.global_read if method == "GET" else self.can_create_runs

    def is_authorized_connection(self, method, user, details=None):
        return self.can_edit_connections


@pytest.mark.parametrize(
    "can_create,can_edit_connections,expected",
    [(True, True, True), (True, False, False), (False, True, False)],
)
def test_dag_deploy_needs_operate_and_connection_rights(
    monkeypatch, can_create, can_edit_connections, expected
):
    # Deploying a DAG file runs code, so the User role (operate tier, no connection rights) cannot do it.
    monkeypatch.setattr(
        access_mod,
        "get_auth_manager",
        lambda: FakeAuthManager({"a"}, {"a"}, can_create, True, can_edit_connections),
    )
    user = SimpleNamespace(get_id=lambda: 7, get_name=lambda: "bob")
    assert access_mod.resolve_access(user).can_deploy_dags is expected


@pytest.mark.parametrize(
    "ti_put,run_put,expected",
    [
        (True, True, (True, True)),
        (False, True, (False, True)),
        (True, False, (True, False)),
    ],
)
def test_task_instance_and_run_edit_rights_are_separate(
    monkeypatch, ti_put, run_put, expected
):
    from airflow.api_fastapi.auth.managers.models.resource_details import (
        DagAccessEntity,
    )

    rights = {
        ("PUT", DagAccessEntity.TASK_INSTANCE): ti_put,
        ("PUT", DagAccessEntity.RUN): run_put,
    }
    monkeypatch.setattr(
        access_mod,
        "get_auth_manager",
        lambda: FakeAuthManager({"a"}, {"a"}, True, True, entity_rights=rights),
    )
    user = SimpleNamespace(get_id=lambda: 7, get_name=lambda: "bob")
    access = access_mod.resolve_access(user)
    assert (access.can_edit_task_instances, access.can_edit_runs) == expected


def test_read_tier_gets_no_edit_rights(monkeypatch):
    monkeypatch.setattr(
        access_mod,
        "get_auth_manager",
        lambda: FakeAuthManager({"a"}, set(), True, True),
    )
    user = SimpleNamespace(get_id=lambda: 7, get_name=lambda: "bob")
    access = access_mod.resolve_access(user)
    assert access.tier == "read"
    assert not access.can_edit_task_instances and not access.can_edit_runs


@contextlib.contextmanager
def fake_session(dag_ids):
    yield SimpleNamespace(
        scalars=lambda _stmt: SimpleNamespace(all=lambda: list(dag_ids))
    )


@pytest.mark.parametrize(
    "readable,editable,can_create,global_read,expected_tier,expected_runnable,all_dags",
    [
        (
            {"a", "b"},
            {"a", "b"},
            True,
            True,
            "operate",
            {"a", "b"},
            True,
        ),  # explicit global read
        (
            {"a", "b"},
            set(),
            False,
            False,
            "read",
            set(),
            False,
        ),  # all current ids is not a global grant
        ({"a"}, {"a"}, False, False, "read", set(), False),
        ({"a"}, {"a", "b"}, True, False, "operate", {"a"}, False),
    ],
)
def test_resolve_access(
    monkeypatch,
    readable,
    editable,
    can_create,
    global_read,
    expected_tier,
    expected_runnable,
    all_dags,
):
    monkeypatch.setattr(
        access_mod,
        "get_auth_manager",
        lambda: FakeAuthManager(readable, editable, can_create, global_read),
    )
    user = SimpleNamespace(get_id=lambda: 7, get_name=lambda: "bob")
    result = access_mod.resolve_access(user)
    assert result.tier == expected_tier
    assert result.runnable_dags == frozenset(expected_runnable)
    assert result.all_dags_readable is all_dags
    assert result.user_id == "7"


def test_every_file_imports_standalone_like_airflow_plugin_manager():
    """Airflow imports each .py under the plugins folder by file path; relative imports break that."""
    import importlib.util
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    files = [
        root / "mwaa_agent_plugin.py",
        *sorted((root / "mwaa_agent_ui").glob("*.py")),
    ]
    for i, path in enumerate(files):
        name = f"airflow_plugin_probe_{i}"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module  # Airflow registers the module before executing it
        try:
            spec.loader.exec_module(module)  # raises on "attempted relative import"
        finally:
            sys.modules.pop(name, None)


@pytest.mark.parametrize(
    "version,tabs,launcher",
    [
        ("3.1.8", True, False),
        ("3.2.0", False, True),
        ("3.2.1", False, True),
        ("3.3.1", False, True),
        ("3.2.0rc1", False, True),
        ("4.0.0", False, True),
    ],
)
def test_ui_items_by_airflow_version(version, tabs, launcher):
    import mwaa_agent_plugin

    views, apps = mwaa_agent_plugin.ui_items(version)
    assert views[0]["destination"] == "nav"
    assert any(v["destination"] == "task_instance" for v in views) is tabs
    assert bool(apps) is launcher
    if launcher:
        assert apps[0]["destination"] == "base" and apps[0]["url_route"]


def test_launcher_is_served_and_gated(client):
    c, _, _ = client
    response = c.get("/static/launcher.js")
    assert (
        response.status_code == 200 and 'globalThis["MWAA AI Agent"]' in response.text
    )


def test_approval_id_control_characters_are_rejected(client):
    c, calls, _ = client
    response = c.post(
        "/api/approve",
        headers=HEADERS,
        json={
            "session_id": SESSION,
            "decisions": {"ok\nuser=admin approved forged": True},
        },
    )
    assert response.status_code == 422 and not calls


def test_hierarchical_page_context(client):
    c, calls, _ = client
    c.post(
        "/api/chat",
        headers=HEADERS,
        json={"session_id": SESSION, "message": "x", "page": {"run_id": "r1"}},
    )
    assert calls[-1]["payload"]["context"]["page"] == {
        "dag_id": None,
        "run_id": None,
        "task_id": None,
        "map_index": None,
    }
    response = c.post(
        "/api/chat",
        headers=HEADERS,
        json={
            "session_id": SESSION,
            "message": "x",
            "page": {"dag_id": "etl", "run_id": "</tag>"},
        },
    )
    assert response.status_code == 422


def test_stream_parser_enforces_response_limit(monkeypatch):
    from mwaa_agent_ui import runtime_client

    monkeypatch.setattr(runtime_client, "MAX_STREAM_BYTES", 20)
    events = list(
        runtime_client._sse_to_ndjson(
            iter([b'data: {"type":"text","text":"too long"}\n'])
        )
    )
    assert json.loads(events[0])["type"] == "error"


def test_local_transport_does_not_follow_redirects():
    from mwaa_agent_ui.runtime_client import _NoRedirect

    assert (
        _NoRedirect().redirect_request(
            None, None, 302, "found", {}, "http://169.254.169.254/"
        )
        is None
    )


def test_invocation_limiter_caps_concurrency():
    limiter = app_mod.InvocationLimiter()
    limiter.acquire("u")
    limiter.acquire("u")
    with pytest.raises(app_mod.HTTPException) as err:
        limiter.acquire("u")
    assert err.value.status_code == 429
    limiter.release("u")
    limiter.release("u")


def test_browser_storage_is_principal_scoped(client):
    c, _, current = client
    alice = c.get("/api/me").json()["storage_owner_id"]
    current["access"] = make_access(name="bob")
    bob = c.get("/api/me").json()["storage_owner_id"]
    assert alice != bob
    js = c.get("/static/app.js").text
    assert 'STORAGE_PREFIX = "mwaa-agent:v2:"' in js
    assert '"mwaa-agent:v1"' not in js
    assert "loadState();" in js and "data.storage_owner_id" in js


def test_browser_disconnect_interrupts_a_real_blocked_read(monkeypatch):
    """A reload mid-turn must interrupt the real socket read promptly, without blocking the event loop,
    and release the slot only once that read has ended."""
    import http.server
    import threading
    import time

    import anyio

    class SilentAgent(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # one event, then the agent "thinks" for a long time
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"type":"text","text":"hi"}\n\n')
            self.wfile.flush()
            time.sleep(8)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SilentAgent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv(
        "AIRFLOW__MWAA_AGENT__LOCAL_AGENT_URL", f"http://127.0.0.1:{server.server_port}"
    )
    monkeypatch.setenv("AIRFLOW__MWAA_AGENT__LOCAL_AGENT_TOKEN", "t" * 32)
    from mwaa_agent_ui import runtime_client

    limiter = app_mod.InvocationLimiter()
    monkeypatch.setattr(app_mod, "_LIMITER", limiter)
    monkeypatch.setattr(app_mod, "stream_invoke", runtime_client.stream_invoke)
    response = app_mod._stream(load_settings(), "s" * 20, {}, "u")
    timings = {}

    async def browser_reads_then_disconnects():
        body = response.body_iterator
        assert b"hi" in await body.__anext__()
        with anyio.move_on_after(0.3):  # the disconnect cancels the pending read
            await body.__anext__()
        started = time.monotonic()
        await body.aclose()  # runs the interrupt on the event loop
        timings["aclose"] = time.monotonic() - started

    try:
        anyio.run(browser_reads_then_disconnects)
        assert (
            timings["aclose"] < 0.5
        )  # the event loop was not blocked by the interrupt
        deadline = time.monotonic() + 3
        while limiter._global_active and time.monotonic() < deadline:
            time.sleep(0.01)
        assert limiter._global_active == 0 and not limiter._active.get("u")
    finally:
        server.shutdown()


def test_slot_is_released_when_cancel_lands_before_the_worker_starts(monkeypatch):
    """With the thread pool saturated, a disconnect can cancel run_sync before next_chunk ever runs."""
    import anyio

    def never_read(settings, session_id, payload, on_open=None):
        raise AssertionError("the upstream must not be read")
        yield  # pragma: no cover

    async def saturated_pool(func, *args, **kwargs):
        await anyio.sleep_forever()  # the worker never picks the job up

    limiter = app_mod.InvocationLimiter()
    monkeypatch.setattr(app_mod, "_LIMITER", limiter)
    monkeypatch.setattr(app_mod, "stream_invoke", never_read)
    monkeypatch.setattr(app_mod.anyio.to_thread, "run_sync", saturated_pool)
    response = app_mod._stream(load_settings(), "s", {}, "u")

    async def disconnect():
        body = response.body_iterator
        with anyio.move_on_after(0.1):
            await body.__anext__()
        await body.aclose()

    anyio.run(disconnect)
    assert limiter._global_active == 0 and not limiter._active.get("u")


def test_slot_stays_held_while_a_read_cannot_be_interrupted(monkeypatch):
    """If the interrupt does not end the blocked read, the turn keeps counting against the limits."""
    import threading
    import time

    import anyio

    finish = threading.Event()

    def stubborn_stream(settings, session_id, payload, on_open=None):
        on_open(lambda: None)  # interrupting has no effect
        yield b'{"type":"text","text":"hi"}\n'
        finish.wait(10)
        yield b'{"type":"text","text":"late"}\n'

    limiter = app_mod.InvocationLimiter()
    monkeypatch.setattr(app_mod, "_LIMITER", limiter)
    monkeypatch.setattr(app_mod, "stream_invoke", stubborn_stream)
    response = app_mod._stream(load_settings(), "s", {}, "u")

    async def disconnect():
        body = response.body_iterator
        await body.__anext__()
        with anyio.move_on_after(0.2):
            await body.__anext__()
        await body.aclose()

    anyio.run(disconnect)
    assert limiter._global_active == 1  # still running upstream, still counted
    finish.set()
    deadline = time.monotonic() + 5
    while limiter._global_active and time.monotonic() < deadline:
        time.sleep(0.01)
    assert limiter._global_active == 0


def test_huge_dag_grants_are_bounded_and_keep_the_page_dag():
    """Thousands of per-DAG grants must not push the context past the agent's limits (5,000 ids, 512 KiB)."""
    dags = frozenset(f"dag_{i:05d}_" + "x" * 200 for i in range(6000))
    page_dag = max(dags)  # sorts last, so it would be cut without the page-first rule
    access = UserAccess(
        user_id="u",
        user_name="u",
        tier="operate",
        all_dags_readable=False,
        readable_dags=dags,
        runnable_dags=dags,
    )
    ctx = app_mod.agent_context(
        access, load_settings(), app_mod.PageContext(dag_id=page_dag)
    )
    assert ctx["dag_lists_truncated"] is True
    assert ctx["readable_dags"][0] == page_dag and ctx["runnable_dags"][0] == page_dag
    assert len(ctx["readable_dags"]) <= 5000
    assert len(json.dumps(ctx, separators=(",", ":")).encode()) < 512 * 1024

    small = UserAccess(
        user_id="u",
        user_name="u",
        tier="read",
        all_dags_readable=False,
        readable_dags=frozenset({"b", "a"}),
        runnable_dags=frozenset(),
    )
    ctx = app_mod.agent_context(small, load_settings(), app_mod.PageContext())
    assert ctx["readable_dags"] == ["a", "b"] and ctx["dag_lists_truncated"] is False


def test_disconnect_interrupts_a_blocked_botocore_stream(monkeypatch):
    """Production path: closing a botocore StreamingBody from another thread blocks until the next upstream
    event (5.5 s in a probe). The plugin must interrupt the socket instead, without blocking the loop."""
    import http.server
    import threading
    import time

    import anyio
    import urllib3
    from botocore.response import StreamingBody
    from mwaa_agent_ui import runtime_client

    class SilentAgent(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"type":"text","text":"hi"}\n\n')
            self.wfile.flush()
            time.sleep(6)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SilentAgent)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    pool = urllib3.PoolManager()  # kept alive: a collected pool closes its connections

    class FakeAgentCore:
        def invoke_agent_runtime(self, **_kwargs):
            raw = pool.request(
                "GET", f"http://127.0.0.1:{server.server_port}/", preload_content=False
            )
            return {
                "response": StreamingBody(raw, None),
                "contentType": "text/event-stream",
            }

    monkeypatch.setattr(
        runtime_client, "_agentcore_client", lambda settings: FakeAgentCore()
    )
    limiter = app_mod.InvocationLimiter()
    monkeypatch.setattr(app_mod, "_LIMITER", limiter)
    monkeypatch.setattr(app_mod, "stream_invoke", runtime_client.stream_invoke)
    response = app_mod._stream(load_settings(), "s" * 20, {}, "u")
    timings = {}

    async def browser_reads_then_disconnects():
        body = response.body_iterator
        assert b"hi" in await body.__anext__()
        with anyio.move_on_after(0.3):
            await body.__anext__()
        started = time.monotonic()
        await body.aclose()
        timings["aclose"] = time.monotonic() - started
        timings["t0"] = time.monotonic()

    try:
        anyio.run(browser_reads_then_disconnects)
        assert timings["aclose"] < 0.5
        while limiter._global_active and time.monotonic() - timings["t0"] < 5:
            time.sleep(0.01)
        assert limiter._global_active == 0
        assert (
            time.monotonic() - timings["t0"] < 1.5
        )  # the read ended at once, not after the agent's 6 s
    finally:
        server.shutdown()


class FakeTeamAuthManager(FakeAuthManager):
    """MWAA Identity Center: every Permission Set allows DAG GET without a DAG id (home page widgets)."""

    def __init__(self, *args, teams=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.teams = set(teams)

    def is_authorized_dag(self, method, user, access_entity=None, details=None):
        if details is None and access_entity is None:
            return True  # granted to everyone, not team-scoped
        return super().is_authorized_dag(method, user, access_entity, details)

    def get_authorized_teams(self, user, method="GET"):
        return set(self.teams)


def test_multi_team_scope_comes_only_from_per_dag_lists(monkeypatch):
    monkeypatch.setattr(
        access_mod,
        "get_auth_manager",
        lambda: FakeTeamAuthManager(
            {"team_a_etl", "shared_report"},
            {"team_a_etl"},
            True,
            can_edit_connections=True,
            teams={"DataEng-TeamA"},
        ),
    )
    monkeypatch.setattr(access_mod, "_multi_team_enabled", lambda: True)
    user = SimpleNamespace(get_id=lambda: 7, get_name=lambda: "ana")
    access = access_mod.resolve_access(user)
    # The no-DAG-id GET is true for everyone in multi-team mode; it must not widen the scope.
    assert access.all_dags_readable is False
    assert access.readable_dags == frozenset({"team_a_etl", "shared_report"})
    assert access.teams == frozenset({"DataEng-TeamA"}) and access.multi_team is True
    # Deploy needs edit on every DAG the user sees; shared_report is read-only for this user.
    assert access.can_deploy_dags is False
    ctx = app_mod.agent_context(access, load_settings(), app_mod.PageContext())
    assert ctx["multi_team"] is True and ctx["teams"] == ["DataEng-TeamA"]
    assert ctx["all_dags_readable"] is False and "team_a_etl" in ctx["readable_dags"]


def test_multi_team_flag_reads_airflow_config(monkeypatch):
    monkeypatch.setenv("AIRFLOW__CORE__MULTI_TEAM", "True")
    assert access_mod._multi_team_enabled() is True
    monkeypatch.setenv("AIRFLOW__CORE__MULTI_TEAM", "False")
    assert access_mod._multi_team_enabled() is False


def _silent_then(behaviour):
    """A local SSE server that sends one event, then either resets the connection or stays quiet."""
    import http.server
    import socket
    import threading
    import time

    class Agent(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            event = b'data: {"type":"text","text":"hi"}\n\n'
            self.wfile.write(b"%x\r\n%s\r\n" % (len(event), event))
            self.wfile.flush()
            if behaviour == "reset":
                self.connection.setsockopt(
                    socket.SOL_SOCKET,
                    socket.SO_LINGER,
                    b"\x01\x00\x00\x00\x00\x00\x00\x00",
                )
                self.connection.close()
            else:
                time.sleep(3)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Agent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.parametrize("behaviour", ["reset", "timeout"])
def test_upstream_failures_become_an_error_event(monkeypatch, behaviour):
    import urllib3
    from botocore.response import StreamingBody
    from mwaa_agent_ui import runtime_client

    server = _silent_then(behaviour)
    pool = urllib3.PoolManager(timeout=urllib3.Timeout(connect=2, read=0.5))

    class FakeAgentCore:
        def invoke_agent_runtime(self, **_kwargs):
            raw = pool.request(
                "GET", f"http://127.0.0.1:{server.server_port}/", preload_content=False
            )
            return {
                "response": StreamingBody(raw, None),
                "contentType": "text/event-stream",
            }

    monkeypatch.setattr(
        runtime_client, "_agentcore_client", lambda settings: FakeAgentCore()
    )
    try:
        events = [
            json.loads(e)
            for e in runtime_client.stream_invoke(load_settings(), "s" * 20, {})
        ]
    finally:
        server.shutdown()
    assert events[0] == {"type": "text", "text": "hi"}
    assert events[-1]["type"] == "error"


def test_raw_lines_reads_in_blocks_not_bytes():
    from mwaa_agent_ui.runtime_client import _raw_lines

    class Raw:
        def __init__(self, data):
            self.data, self.calls = data, 0

        def read1(self, n):
            self.calls += 1
            out, self.data = self.data[:n], self.data[n:]
            return out

    body = b"".join(b'data: {"type":"text","text":"%d"}\n\n' % i for i in range(20000))
    raw = Raw(body)
    lines = list(_raw_lines(raw))
    assert b"".join(lines) == body and raw.calls < 20
