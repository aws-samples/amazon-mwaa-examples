# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Tests for reading DAG folders (dag_files), linting DAG files (dag_lint), and the tools built on them."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from types import SimpleNamespace

import pytest
from factories import _ENV_FACTS, TEAMS_ENV, payload
from mwaa_agent import dag_files, dag_lint
from mwaa_agent import tools as t
from mwaa_agent.context import parse_request
from mwaa_agent.dag_deploy import DagDeployError, validate_dag_file
from mwaa_agent.session import describe_tool_call

AIRFLOW2_DAG = """from datetime import datetime
from airflow import DAG
from airflow.operators.dummy import DummyOperator

with DAG("legacy", schedule_interval="@daily", start_date=datetime(2024, 1, 1)) as dag:
    a = DummyOperator(task_id="a")
"""

AIRFLOW3_DAG = """from datetime import datetime

from airflow.sdk import dag, task


@dag(schedule=None, start_date=datetime(2024, 1, 1), catchup=False)
def ok():
    @task
    def hello():
        print("hi")

    hello()


ok()
"""


def _ctx(**context):
    return parse_request(payload(context=context)).context


# --- Paths ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "../x.py",
        "/abs.py",
        "a/../b.py",
        "a//b.py",
        "x.txt",
        ".hidden.py",
        "sub/.hidden/x.py",
        "__pycache__/x.py",
        "a/" * 8 + "x.py",
        "x py.py",
        "caf\u00e9.py",
        None,
    ],
)
def test_validate_relative_path_rejects(path):
    with pytest.raises(dag_files.DagFileError):
        dag_files.validate_relative_path(path)


def test_validate_relative_path_accepts_nested_files():
    assert dag_files.validate_relative_path("etl/orders_v2.py") == "etl/orders_v2.py"


# --- Local folder -----------------------------------------------------------------------------------


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / "authored"
    (root / "etl").mkdir(parents=True)
    (root / "etl" / "orders.py").write_text(AIRFLOW3_DAG)
    (root / "legacy.py").write_text(AIRFLOW2_DAG)
    (root / "notes.txt").write_text("not python")
    (root / ".upload-x.tmp.py").write_text("temp")
    (root / "has space.py").write_text("x = 1\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "x.py").write_text("cache")
    (tmp_path / "secret.py").write_text("outside")
    (root / "link.py").symlink_to(tmp_path / "secret.py")
    (root / "linkdir").symlink_to(tmp_path, target_is_directory=True)
    return root


def test_local_list_shows_only_readable_python_files(folder):
    local = dag_files.local_folder(str(folder))
    files, truncated = local.list_files()
    assert [f["path"] for f in files] == ["legacy.py", "etl/orders.py"]
    assert not truncated and files[0]["bytes"] == len(AIRFLOW2_DAG.encode())
    for entry in files:
        local.read(entry["path"])  # everything listed can be read


def test_local_list_truncates_by_entries_and_by_scanned_files(folder, monkeypatch):
    monkeypatch.setattr(dag_files, "MAX_LIST_ENTRIES", 1)
    files, truncated = dag_files.local_folder(str(folder)).list_files()
    assert len(files) == 1 and truncated
    monkeypatch.setattr(dag_files, "MAX_LIST_ENTRIES", 500)
    monkeypatch.setattr(dag_files, "MAX_LIST_SCANNED", 1)
    assert dag_files.local_folder(str(folder)).list_files()[1]


def test_local_read(folder):
    source = dag_files.local_folder(str(folder)).read("etl/orders.py")
    assert source.content == AIRFLOW3_DAG and not source.truncated and source.sha256


@pytest.mark.parametrize("path", ["link.py", "linkdir/secret.py", "missing.py"])
def test_local_read_refuses_links_and_missing_files(folder, path):
    with pytest.raises(dag_files.DagFileError):
        dag_files.local_folder(str(folder)).read(path)


def test_local_read_truncates_large_files(folder, monkeypatch):
    monkeypatch.setattr(dag_files, "MAX_READ_BYTES", 10)
    source = dag_files.local_folder(str(folder)).read("legacy.py")
    assert source.truncated and source.sha256 is None
    assert len(source.content) == 10 and source.size == len(AIRFLOW2_DAG.encode())


# --- S3 folder --------------------------------------------------------------------------------------


class FakeS3:
    """Enough of the S3 client for paged listings and ranged reads, with S3's edge cases."""

    class ClientError(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    exceptions = SimpleNamespace(ClientError=ClientError)
    PAGE_SIZE = 2

    def __init__(self, objects):
        self.objects, self.calls = objects, []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        fake = self

        class Paginator:
            def paginate(self, **kw):
                fake.calls.append(("list", kw))
                keys = sorted(k for k in fake.objects if k.startswith(kw["Prefix"]))
                keys = keys[: kw["PaginationConfig"]["MaxItems"]]
                for i in range(0, len(keys), fake.PAGE_SIZE):
                    yield {
                        "Contents": [
                            {"Key": k, "Size": len(fake.objects[k])}
                            for k in keys[i : i + fake.PAGE_SIZE]
                        ]
                    }

        return Paginator()

    def get_object(self, **kw):
        self.calls.append(("get", kw))
        if kw["Key"] not in self.objects:
            raise self.ClientError("NoSuchKey")
        data = self.objects[kw["Key"]]
        if not data:
            raise self.ClientError(
                "InvalidRange"
            )  # S3 refuses any range on an empty object
        end = int(kw["Range"].split("-")[1])
        body = SimpleNamespace(
            read=lambda n: data[: min(n, end + 1)], close=lambda: None
        )
        return {
            "Body": body,
            "ContentRange": f"bytes 0-{min(end, len(data) - 1)}/{len(data)}",
        }


def test_s3_list_and_read_stay_in_the_folder():
    s3 = FakeS3(
        {
            "dags/a.py": b"x = 1\n",
            "dags/sub/b.py": b"y = 2\n",
            "dags/.airflowignore": b"x",
            "dags/notes.md": b"x",
            "dags/c.py": b"z = 3\n",
            "plugins.zip": b"x",
            "startup.sh": b"x",
        }
    )
    folder = dag_files.s3_folder(s3, "bkt", "dags/", "111122223333")
    files, truncated = folder.list_files()  # spans several pages
    assert [f["path"] for f in files] == ["a.py", "c.py", "sub/b.py"] and not truncated
    assert folder.read("sub/b.py").content == "y = 2\n"
    list_call, get_call = s3.calls[0][1], s3.calls[1][1]
    assert list_call["Prefix"] == "dags/"
    assert list_call["ExpectedBucketOwner"] == "111122223333"
    assert get_call["Key"] == "dags/sub/b.py"
    assert get_call["ExpectedBucketOwner"] == "111122223333"
    with pytest.raises(dag_files.DagFileError, match="does not exist"):
        folder.read("missing.py")


def test_s3_read_reports_full_size_when_truncated(monkeypatch):
    monkeypatch.setattr(dag_files, "MAX_READ_BYTES", 4)
    s3 = FakeS3({"dags/a.py": b"0123456789"})
    source = dag_files.s3_folder(s3, "bkt", "dags", None).read("a.py")
    assert source.truncated and source.size == 10 and source.content == "0123"


def test_s3_reads_empty_files():
    s3 = FakeS3({"dags/pkg/__init__.py": b""})
    source = dag_files.s3_folder(s3, "bkt", "dags", None).read("pkg/__init__.py")
    assert source.content == "" and source.size == 0 and not source.truncated


def test_s3_listing_is_bounded_by_scanned_entries(monkeypatch):
    monkeypatch.setattr(dag_files, "MAX_LIST_SCANNED", 3)
    objects = {f"dags/f{i}.txt": b"x" for i in range(6)} | {"dags/z.py": b"x"}
    folder = dag_files.s3_folder(FakeS3(objects), "bkt", "dags", None)
    files, truncated = folder.list_files()
    assert files == [] and truncated  # z.py is past the scan budget


def test_s3_folder_refuses_the_bucket_root():
    with pytest.raises(dag_files.DagFileError):
        dag_files.s3_folder(FakeS3({}), "bkt", "", None)


# --- Who may read which folder ----------------------------------------------------------------------


@pytest.fixture
def mwaa(monkeypatch):
    monkeypatch.delenv("AIRFLOW_API_BASE_URL", raising=False)
    monkeypatch.setattr(t._RESOURCES, "environment", lambda ctx: dict(_ENV_FACTS))
    monkeypatch.setattr(t.boto3, "client", lambda *a, **k: FakeS3({}))
    return monkeypatch


def test_mwaa_folder_needs_read_access_to_all_dags(mwaa):
    with pytest.raises(dag_files.DagFileError, match="dagSources"):
        t.readable_dag_folder(_ctx(all_dags_readable=False))
    folder = t.readable_dag_folder(_ctx(all_dags_readable=True))
    assert folder.describe == "s3://env-bucket/dags/"


def test_team_folders_only_for_the_users_own_teams(mwaa):
    mwaa.setattr(
        t._RESOURCES, "environment", lambda ctx: dict(_ENV_FACTS, teams=TEAMS_ENV)
    )
    ctx = _ctx(multi_team=True, teams=["DataEng-TeamA"], all_dags_readable=True)
    assert t.readable_dag_folder(ctx, "DataEng-TeamA").describe == (
        "s3://acme-airflow/teams/DataEng-TeamA/"
    )
    # Not a member and no such team get the same message, so it does not reveal team names.
    messages = set()
    for team in ("DataEng-TeamB", "NoSuchTeam"):
        with pytest.raises(dag_files.DagFileError) as err:
            t.readable_dag_folder(ctx, team)
        messages.add(str(err.value).replace(team, "<team>"))
    assert len(messages) == 1
    with pytest.raises(dag_files.DagFileError, match="team="):
        t.readable_dag_folder(ctx)  # the global folder mixes teams


def test_local_folder_needs_read_access_to_all_dags(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRFLOW_API_BASE_URL", "http://webserver:8080")
    monkeypatch.setenv("MWAA_AGENT_LOCAL_DAGS_DIR", str(tmp_path))
    with pytest.raises(dag_files.DagFileError):
        t.readable_dag_folder(_ctx(all_dags_readable=False))
    assert (
        t.readable_dag_folder(_ctx(all_dags_readable=True)).describe == "dags/authored"
    )


# --- Lint -------------------------------------------------------------------------------------------


def test_lint_reports_airflow3_breakage_by_category():
    result = dag_lint.lint_source(AIRFLOW2_DAG, "legacy.py")
    codes = {f.code for f in result.findings}
    assert {"AIR301", "AIR302"} <= codes
    removed = next(f for f in result.findings if f.code == "AIR301")
    assert removed.category.startswith("breaks on Airflow 3") and removed.line == 5
    assert result.fixed_content is None


def test_lint_clean_dag_has_no_breaking_findings():
    result = dag_lint.lint_source(AIRFLOW3_DAG)
    assert not [
        f for f in result.findings if f.category.startswith(("breaks", "error"))
    ]


def test_lint_syntax_error_is_reported_not_raised():
    result = dag_lint.lint_source("def broken(:\n    pass\n")
    assert result.findings
    assert result.findings[0].category == "error: the file will not import"


def test_lint_fix_applies_safe_fixes_and_reports_the_old_import():
    result = dag_lint.lint_source(AIRFLOW2_DAG, fix=True)
    fixed = result.fixed_content
    assert fixed and "schedule=" in fixed and "schedule_interval" not in fixed
    assert "EmptyOperator" in fixed
    # The old import stays in the file but is reported, so the model removes it by hand.
    leftovers = [f for f in result.fixed_findings if f.code == "F401"]
    assert leftovers and "airflow.operators.dummy" in leftovers[0].message


def test_lint_fix_keeps_side_effect_imports():
    result = dag_lint.lint_source("import company.listeners\n" + AIRFLOW2_DAG, fix=True)
    assert "import company.listeners" in result.fixed_content
    # Unused imports outside Airflow are not findings either.
    assert not [f for f in result.findings if "company" in f.message]


@pytest.mark.parametrize("content", ["", "   ", None, "x = 1\n" * 20_000])
def test_lint_rejects_empty_or_oversized_content(content):
    with pytest.raises(dag_lint.DagLintError):
        dag_lint.lint_source(content)


def test_lint_never_passes_a_caller_path_to_ruff(monkeypatch):
    seen = {}

    def fake_run(args, **kw):
        seen["args"], seen["kw"] = args, kw
        return subprocess.CompletedProcess(args, 0, b"[]", b"")

    monkeypatch.setattr(dag_lint.subprocess, "run", fake_run)
    dag_lint.lint_source("x = 1\n", "../../etc/passwd")
    args = seen["args"]
    assert args[args.index("--stdin-filename") + 1] == "dag.py"
    assert "--isolated" in args and args[-1] == "-"
    assert seen["kw"]["env"].keys() == {"HOME", "PATH"} and seen["kw"]["timeout"]


@pytest.mark.parametrize(
    "outcome,needle",
    [
        (subprocess.CompletedProcess([], 2, b"", b"echoed source"), "exit code 2"),
        (subprocess.TimeoutExpired("ruff", 30), "did not finish"),
        (subprocess.CompletedProcess([], 0, b"not json", b""), "not JSON"),
    ],
)
def test_lint_failures_are_reported_without_ruff_output(monkeypatch, outcome, needle):
    def fake_run(args, **kw):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(dag_lint.subprocess, "run", fake_run)
    with pytest.raises(dag_lint.DagLintError, match=needle) as err:
        dag_lint.lint_source("x = 1\n")
    assert "echoed" not in str(err.value)


def test_ruff_binary_without_execute_bit_runs_from_a_private_copy(
    tmp_path, monkeypatch
):
    import ruff

    original = tmp_path / "ruff"
    original.write_bytes(b"#!/bin/sh\n")
    original.chmod(stat.S_IRUSR)
    monkeypatch.setattr(ruff, "find_ruff_bin", lambda: str(original))
    dag_lint.ruff_binary.cache_clear()
    try:
        path = dag_lint.ruff_binary()
        assert path != str(original) and os.access(path, os.X_OK)
        assert not os.access(original, os.X_OK)  # the package copy is left alone
    finally:
        dag_lint.ruff_binary.cache_clear()


def test_deploy_refuses_content_built_from_redacted_output():
    with pytest.raises(DagDeployError, match="REDACTED"):
        validate_dag_file("x.py", 'PASSWORD = "[REDACTED]"\n')


# --- Tools ------------------------------------------------------------------------------------------


@pytest.fixture
def local_tools(folder, tmp_path, monkeypatch):
    monkeypatch.setenv("AIRFLOW_API_BASE_URL", "http://webserver:8080")
    monkeypatch.setenv("MWAA_AGENT_LOCAL_DAGS_DIR", str(folder))
    ctx = _ctx(all_dags_readable=True)
    return {tool.tool_name: tool for tool in t.build_tools(lambda: ctx, tmp_path)}


def test_list_and_read_tools(local_tools):
    listing = json.loads(local_tools["list_dag_files"]())
    assert [f["path"] for f in listing["files"]] == ["legacy.py", "etl/orders.py"]
    read = json.loads(local_tools["read_dag_file"]("etl/orders.py"))
    assert read["content"] == AIRFLOW3_DAG and "redacted" not in read
    denied = json.loads(local_tools["read_dag_file"]("../secret.py"))
    assert denied["error"] == "DeniedByAgentPolicy"


def test_read_tool_flags_redacted_secrets(local_tools, folder):
    (folder / "leaky.py").write_text('URI = "postgresql://user:hunter2@db/app"\n')
    read = json.loads(local_tools["read_dag_file"]("leaky.py"))
    assert "hunter2" not in read["content"] and "redacted" in read
    assert read["redeployable_with_deploy_dag"] is False


def test_redeployable_only_for_whole_top_level_files(local_tools):
    top = json.loads(local_tools["read_dag_file"]("legacy.py"))
    assert top["redeployable_with_deploy_dag"] is True
    nested = json.loads(local_tools["read_dag_file"]("etl/orders.py"))
    assert nested["redeployable_with_deploy_dag"] is False


def test_read_result_never_cuts_the_middle_of_a_file(local_tools, folder):
    # Non-ASCII characters become \uXXXX in JSON, so a file under the byte limit can exceed the
    # character limit of a tool result.
    (folder / "wide.py").write_text("# " + "\u0436" * 40_000 + "\nx = 1\n")
    output = local_tools["read_dag_file"]("wide.py")
    read = json.loads(output)  # still valid JSON
    assert read["truncated"] and read["sha256"] is None
    assert read["redeployable_with_deploy_dag"] is False
    assert len(output) <= t.MAX_DAG_READ_CHARS


def test_lint_tool_by_path_and_by_content(local_tools):
    by_path = json.loads(local_tools["lint_dag"](path="legacy.py"))
    assert by_path["path"] == "legacy.py" and by_path["counts"]
    assert by_path["airflow_version"] == "3.1.8"
    by_content = json.loads(local_tools["lint_dag"](content=AIRFLOW2_DAG, fix=True))
    assert "fixed_content" in by_content and by_content["fixed_content_findings"]
    for kwargs in ({}, {"content": "x = 1\n", "path": "legacy.py"}):
        assert (
            json.loads(local_tools["lint_dag"](**kwargs))["error"]
            == "DeniedByAgentPolicy"
        )


def test_lint_flags_redacted_fixed_content(local_tools):
    leaky = AIRFLOW2_DAG + 'URI = "postgresql://user:hunter2@db/app"\n'
    result = json.loads(local_tools["lint_dag"](content=leaky, fix=True))
    assert "hunter2" not in result["fixed_content"]
    assert "fixed_content_redacted" in result


def test_s3_tools_read_only_the_users_team_folder(mwaa, tmp_path):
    s3 = FakeS3(
        {
            "teams/DataEng-TeamA/a.py": b"x = 1\n",
            "teams/DataEng-TeamB/b.py": b"y = 2\n",
        }
    )
    mwaa.setattr(
        t._RESOURCES, "environment", lambda ctx: dict(_ENV_FACTS, teams=TEAMS_ENV)
    )
    mwaa.setattr(t.boto3, "client", lambda *a, **k: s3)
    ctx = _ctx(multi_team=True, teams=["DataEng-TeamA"], all_dags_readable=True)
    tools = {tool.tool_name: tool for tool in t.build_tools(lambda: ctx, tmp_path)}
    listing = json.loads(tools["list_dag_files"](team="DataEng-TeamA"))
    assert [f["path"] for f in listing["files"]] == ["a.py"]
    read = json.loads(tools["read_dag_file"]("a.py", team="DataEng-TeamA"))
    assert read["content"] == "x = 1\n"
    other = json.loads(tools["read_dag_file"]("b.py", team="DataEng-TeamB"))
    assert other["error"] == "DeniedByAgentPolicy"
    touched = [call[1].get("Prefix") or call[1].get("Key") for call in s3.calls]
    assert touched and all(p.startswith("teams/DataEng-TeamA/") for p in touched)


def test_inline_lint_content_is_not_provenance(mwaa, tmp_path):
    # Only real DAG source may vouch for resource names; the model's own text must not.
    ctx = _ctx(all_dags_readable=True)
    tools = {tool.tool_name: tool for tool in t.build_tools(lambda: ctx, tmp_path)}
    tools["lint_dag"](content='GlueJobOperator(job_name="payroll_export")\n')
    out = json.loads(tools["aws_api"]("glue", "GetJob", {"JobName": "payroll_export"}))
    assert out["error"] == "DeniedByAgentPolicy"
    assert (
        "rendered fields" in out["message"]
    )  # refused for provenance, not for another reason


def test_tool_lines_never_show_file_content():
    line = describe_tool_call("lint_dag", {"content": AIRFLOW2_DAG, "fix": True})
    assert "DummyOperator" not in line and "bytes" in line and "with fixes" in line
    assert (
        describe_tool_call("read_dag_file", {"path": "a.py", "team": "T1"})
        == "a.py (team T1)"
    )
