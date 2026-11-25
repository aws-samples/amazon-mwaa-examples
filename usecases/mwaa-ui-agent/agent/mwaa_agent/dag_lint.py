# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Static checks for DAG files with Ruff's Airflow rules.

Ruff parses the source and never imports or runs it, so linting is safe on untrusted DAG code. The binary
comes from the pinned ``ruff`` wheel in the agent package. It runs with a fixed argument list, no shell, no
inherited environment, ``--isolated`` (no configuration files) and a timeout.
"""

from __future__ import annotations

import functools
import json
import os
import shutil
import stat
import subprocess  # nosec B404 - runs only the pinned Ruff binary with fixed arguments; see _run_ruff
import tempfile
from dataclasses import dataclass
from typing import Any

# Largest source the linter accepts: the same as a DAG folder read, so any readable file can be linted.
MAX_LINT_BYTES = 96 * 1024
MAX_FINDINGS = 200
RUFF_TIMEOUT_SECONDS = 30
_MAX_RUFF_OUTPUT_BYTES = 2 * 1024 * 1024

# Rule selection. Preview is on for AIR003, AIR304 and AIR321; Ruff is pinned, so preview rules cannot
# change under us. Pyflakes and syntax rules catch files that would not import at all.
RULES = (
    "E9",  # syntax errors
    "F63",  # invalid comparisons
    "F7",  # statements in the wrong place
    "F82",  # undefined names
    "AIR001",
    "AIR002",
    "AIR003",
    "AIR301",
    "AIR302",
    "AIR303",
    "AIR304",
    "AIR311",
    "AIR312",
    "AIR321",
    # Unused imports, reported only for Airflow modules (see _keep): a safe fix adds the new import but
    # leaves the old one, and an import from a module removed in Airflow 3 fails even when nothing uses it.
    "F401",
)
# The fix pass never removes imports: an unused import can be there for its side effects.
FIX_RULES = tuple(rule for rule in RULES if rule != "F401")

# What each rule family means for the user, so the model does not have to infer it from the code.
_CATEGORIES = {
    "AIR301": "breaks on Airflow 3: removed",
    "AIR302": "breaks on Airflow 3: moved to a provider package",
    "AIR303": "breaks on Airflow 3: changed signature",
    "AIR311": "deprecated in Airflow 3: still works, update recommended",
    "AIR312": "deprecated in Airflow 3: moved to a provider package, still works",
    "AIR321": "moved in Airflow 3.1",
    "AIR304": "best practice: value changes on every DAG parse",
    "AIR003": "best practice: Variable.get() at the top level runs on every DAG parse",
    "AIR001": "best practice: task variable name differs from task_id",
    "AIR002": "best practice: DAG has no explicit schedule",
    "F401": "unused Airflow import: remove it if its module is gone in Airflow 3, or the file will not import",
}


def _keep(code: str, message: str) -> bool:
    """F401 only for Airflow imports; other unused imports are style, or intentional side effects."""
    return code != "F401" or message.startswith("`airflow.")


class DagLintError(Exception):
    """The source cannot be linted. The message is safe to show to the model and user."""


@dataclass(frozen=True)
class Finding:
    code: str
    line: int
    column: int
    message: str
    category: str
    fixable: bool


@dataclass(frozen=True)
class LintResult:
    findings: tuple[Finding, ...]
    truncated: bool
    fixed_content: str | None
    # Findings left in fixed_content: what the safe fixes did not cover.
    fixed_findings: tuple[Finding, ...] = ()


def _category(code: str) -> str:
    if code in _CATEGORIES:
        return _CATEGORIES[code]
    if code.startswith(("E9", "F")):
        return "error: the file will not import"
    return "other"


@functools.cache
def ruff_binary() -> str:
    """The pinned Ruff binary, made executable once if the package extraction dropped the mode bits.

    Cached for the process. Concurrent first calls may each resolve it; the result is the same.
    """
    try:
        from ruff import find_ruff_bin
    except ImportError as err:
        raise DagLintError("Ruff is not installed in this agent package") from err
    try:
        path = find_ruff_bin()
    except FileNotFoundError as err:
        raise DagLintError(
            "the Ruff binary is missing from this agent package"
        ) from err
    if not os.access(path, os.X_OK):
        # Some deployment targets unpack code without execute bits, and the code directory can be
        # read-only, so run a private copy instead of changing the original.
        copy = os.path.join(tempfile.mkdtemp(prefix="mwaa-agent-ruff-"), "ruff")
        shutil.copyfile(path, copy)
        os.chmod(copy, stat.S_IRUSR | stat.S_IXUSR)
        path = copy
    return path


def _run_ruff(content: bytes, file_name: str, fix: bool) -> bytes:
    args = [
        ruff_binary(),
        "check",
        "--isolated",
        "--no-cache",
        "--preview",
        "--exit-zero",
        "--target-version",
        "py312",
        "--select",
        ",".join(FIX_RULES if fix else RULES),
        "--stdin-filename",
        file_name,
    ]
    args += ["--fix", "--quiet"] if fix else ["--output-format", "json"]
    args.append("-")
    with tempfile.TemporaryDirectory(prefix="mwaa-agent-lint-") as workdir:
        try:
            completed = subprocess.run(  # nosec B603 - fixed argv, no shell, source only on stdin
                args,
                input=content,
                capture_output=True,
                cwd=workdir,
                env={"HOME": workdir, "PATH": "/usr/bin:/bin"},
                timeout=RUFF_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as err:
            raise DagLintError(
                f"Ruff did not finish within {RUFF_TIMEOUT_SECONDS} seconds"
            ) from err
        except OSError as err:
            raise DagLintError(f"Ruff could not start ({type(err).__name__})") from err
    if completed.returncode != 0:
        # --exit-zero makes findings exit 0, so any other code is a Ruff failure. Its stderr can echo
        # the source, so report only the exit code.
        raise DagLintError(f"Ruff failed with exit code {completed.returncode}")
    if len(completed.stdout) > _MAX_RUFF_OUTPUT_BYTES:
        raise DagLintError("Ruff output exceeded its size limit")
    return completed.stdout


def _safe_name(file_name: Any) -> str:
    """Ruff uses the name only in messages and for file-type detection; never a path from the caller."""
    name = os.path.basename(file_name) if isinstance(file_name, str) else ""
    if not name.endswith(".py") or not name.isascii() or "\x00" in name:
        return "dag.py"
    return name


def _findings(data: bytes, name: str) -> tuple[list[Finding], bool]:
    try:
        raw = json.loads(_run_ruff(data, name, fix=False) or b"[]")
    except ValueError as err:
        raise DagLintError("Ruff returned output that is not JSON") from err
    findings = []
    for item in raw if isinstance(raw, list) else []:
        code = str(
            item.get("code") or "E999"
        )  # Ruff reports syntax errors with no code
        message = str(item.get("message", ""))
        if not _keep(code, message):
            continue
        location = item.get("location") or {}
        findings.append(
            Finding(
                code=code,
                line=int(location.get("row") or 0),
                column=int(location.get("column") or 0),
                message=message,
                category=_category(code),
                # Only safe fixes count: --fix never applies unsafe ones, and F401 is not in the fix pass.
                fixable=code != "F401"
                and (item.get("fix") or {}).get("applicability") == "safe",
            )
        )
    findings.sort(key=lambda f: (f.line, f.column, f.code))
    return findings[:MAX_FINDINGS], len(findings) > MAX_FINDINGS


def lint_source(
    content: Any, file_name: str = "dag.py", fix: bool = False
) -> LintResult:
    """Lint one DAG file. With ``fix``, also return Ruff's safe fixes and what they leave behind."""
    if not isinstance(content, str) or not content.strip():
        raise DagLintError("content must be the Python source of a DAG file")
    data = content.encode("utf-8")
    if len(data) > MAX_LINT_BYTES:
        raise DagLintError(f"files are limited to {MAX_LINT_BYTES} bytes for linting")
    name = _safe_name(file_name)
    findings, truncated = _findings(data, name)
    if not (fix and any(f.fixable for f in findings)):
        return LintResult(tuple(findings), truncated, None)
    fixed = _run_ruff(data, name, fix=True).decode("utf-8", errors="replace")
    if fixed == content:
        return LintResult(tuple(findings), truncated, None)
    remaining, _ = _findings(fixed.encode("utf-8"), name)
    return LintResult(tuple(findings), truncated, fixed, tuple(remaining))


def result_summary(result: LintResult) -> dict[str, Any]:
    """The tool response: findings grouped by severity first, so the model leads with what breaks."""
    counts: dict[str, int] = {}
    for finding in result.findings:
        counts[finding.category] = counts.get(finding.category, 0) + 1
    summary: dict[str, Any] = {
        "linter": "ruff (Airflow rules AIR*, plus syntax and undefined-name checks)",
        "counts": counts,
        "findings": [
            {
                "code": f.code,
                "line": f.line,
                "column": f.column,
                "category": f.category,
                "message": f.message,
                "fixable": f.fixable,
            }
            for f in result.findings
        ],
    }
    if result.truncated:
        summary["truncated"] = f"only the first {MAX_FINDINGS} findings are shown"
    if result.fixed_content is not None:
        summary["fixed_content"] = result.fixed_content
        summary["fixed_content_findings"] = [
            {
                "code": f.code,
                "line": f.line,
                "category": f.category,
                "message": f.message,
            }
            for f in result.fixed_findings
        ]
        summary["fixed_content_note"] = (
            "Ruff's safe fixes only. fixed_content_findings lists what is left, such as old imports and "
            "findings without a safe fix: change those by hand and lint again before deploying"
        )
    return summary
