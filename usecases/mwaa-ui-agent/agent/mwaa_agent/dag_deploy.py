# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""DAG file validation and deployment for the authoring workflow.

Deployment is off unless ENABLE_DAG_DEPLOY=true on the runtime. Every upload is shown to the user for
approval with the full file content. Files go only to the top level of the environment's DAG folder:
the S3 DagS3Path on MWAA, or MWAA_AGENT_LOCAL_DAGS_DIR in local development.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import io
import os
import re
import tempfile
import threading
import tokenize
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .sanitize import redact

# Small enough that the full file fits in one approval event to the browser.
MAX_DAG_FILE_BYTES = 48 * 1024
# Long lines can push code out of view on the approval card.
MAX_LINE_CHARS = 300
_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\.py$")


def _hidden_character(content: str) -> str | None:
    """The first character that renders invisibly or reorders text, as U+XXXX, or None.

    Covers Unicode format characters (Cf: bidi controls, zero-width spaces, BOM), line and paragraph
    separators, control characters other than tab, newline and carriage return, and a carriage return that
    is not part of CRLF: Python treats a lone CR as a line break, but the browser draws nothing for it, so
    code after "# comment\\r" would look like part of the comment.
    """
    for index, ch in enumerate(content):
        if ch == "\r" and content[index + 1 : index + 2] != "\n":
            return "U+000D"
        if ch in "\t\n\r":
            continue
        if unicodedata.category(ch) in ("Cf", "Cc", "Zl", "Zp") or ch in _BLANK_LOOKING:
            return f"U+{ord(ch):04X}"
        if unicodedata.category(ch) == "Zs" and ch != " ":
            return f"U+{ord(ch):04X}"
    return None


# Letters and symbols that render as blank space (Hangul fillers, braille blank).
_BLANK_LOOKING = frozenset("\u115f\u1160\u3164\uffa0\u2800")


def _non_ascii_identifier(content: str) -> str | None:
    """The first identifier with non-ASCII characters: they can look like another name (Cyrillic 'а')."""
    try:
        for token in tokenize.generate_tokens(io.StringIO(content).readline):
            if token.type == tokenize.NAME and not token.string.isascii():
                return token.string
    except (tokenize.TokenError, SyntaxError):
        return None  # ast.parse reports syntax errors
    return None


class DagDeployError(Exception):
    """The file cannot be deployed. The message is safe to show to the model and user."""


def deploy_enabled() -> bool:
    return os.environ.get("ENABLE_DAG_DEPLOY", "").lower() == "true"


@dataclass(frozen=True)
class DagFile:
    file_name: str
    content: str
    data: bytes
    sha256_hex: str
    has_dag: bool


def validate_dag_file(file_name: Any, content: Any) -> DagFile:
    """Reject anything that is not a single, syntactically valid Python file with a safe name."""
    if (
        not isinstance(file_name, str)
        or not _FILE_NAME.match(file_name)
        or ".." in file_name
    ):
        raise DagDeployError(
            "file_name must be a plain file name ending in .py, such as 'orders_etl.py' "
            "(letters, digits, '_', '-', '.'; no folders)"
        )
    if not isinstance(content, str) or not content.strip():
        raise DagDeployError("content must be the full Python source of the DAG file")
    data = content.encode("utf-8")
    if len(data) > MAX_DAG_FILE_BYTES:
        raise DagDeployError(f"DAG files are limited to {MAX_DAG_FILE_BYTES} bytes")
    if "[REDACTED]" in content:
        # A redacted read (read_dag_file, task logs) would replace the real secret with this marker.
        raise DagDeployError(
            "the file contains [REDACTED], so it was built from redacted output and would lose the original "
            "value. Read credentials from an Airflow connection or AWS Secrets Manager instead"
        )
    if redact(content) != content:
        # The approval card is redacted, so a secret-shaped value would make the user approve something
        # other than what gets written. Hardcoded credentials do not belong in DAG files anyway.
        raise DagDeployError(
            "the file contains a credential-shaped value (password, key, token, or connection URI with a "
            "password). Read credentials from an Airflow connection or AWS Secrets Manager instead"
        )
    hidden = _hidden_character(content)
    if hidden:
        # Bidi controls and zero-width characters make the approval card show different code than Python
        # runs ("Trojan Source"). A DAG file never needs them.
        raise DagDeployError(
            f"the file contains an invisible or text-direction character ({hidden}) that would make the "
            "approval card show different code than what runs. Remove it, or write it as an escape such "
            "as \\u200b inside a string"
        )
    long_line = next(
        (
            n
            for n, line in enumerate(content.splitlines(), 1)
            if len(line) > MAX_LINE_CHARS
        ),
        None,
    )
    if long_line:
        raise DagDeployError(
            f"line {long_line} is longer than {MAX_LINE_CHARS} characters; split it so the whole line is "
            "visible on the approval card"
        )
    try:
        tree = ast.parse(content, filename=file_name)
    except SyntaxError as err:
        raise DagDeployError(
            f"Python syntax error at line {err.lineno}: {err.msg}"
        ) from err
    odd_name = _non_ascii_identifier(content)
    if odd_name:
        raise DagDeployError(
            f"the identifier {odd_name!r} has non-ASCII characters, which can look like a different name "
            "on the approval card. Use ASCII names (non-ASCII text inside strings and comments is fine)"
        )
    return DagFile(
        file_name=file_name,
        content=content,
        data=data,
        sha256_hex=hashlib.sha256(data).hexdigest(),
        has_dag=_defines_dag(tree),
    )


def _defines_dag(tree: ast.AST) -> bool:
    """True if the module constructs DAG(...) or uses the @dag decorator."""
    for node in ast.walk(tree):
        target = None
        if isinstance(node, ast.Call):
            target = node.func
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                name = deco.func if isinstance(deco, ast.Call) else deco
                if (
                    getattr(name, "id", None) == "dag"
                    or getattr(name, "attr", None) == "dag"
                ):
                    return True
        if target is not None and (
            getattr(target, "id", None) == "DAG"
            or getattr(target, "attr", None) == "DAG"
        ):
            return True
    return False


@dataclass(frozen=True)
class DeployTarget:
    """Where a file goes. ``describe`` is shown to the user on the approval card.

    ``state`` returns a version marker for the current file (S3 ETag, or the SHA-256 of a local file), or None
    if there is none. ``write`` takes the state the user approved and fails if the file no longer matches it.
    """

    describe: Callable[[str], str]
    state: Callable[[str], str | None]
    write: Callable[[DagFile, str | None], dict[str, Any]]

    def exists(self, name: str) -> bool:
        return self.state(name) is not None


def _changed_since_approval(name: str) -> DagDeployError:
    return DagDeployError(
        f"{name} changed after the user approved the upload, so nothing was written. Read the DAG folder "
        "again and ask the user to approve a new upload"
    )


class ApprovedDeploys:
    """Binds an approval card to the DAG file state it showed, for the tool call that writes it.

    The approval hook records the target state when it first shows the card, keyed by tool-use ID, and checks
    it again when the approval resumes. The tool then takes that approved state and passes it to the write as
    a precondition, so a card that said "add" cannot end up replacing a file, and a replace cannot clobber a
    newer version.
    """

    MAX_ENTRIES = 100

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._shown: dict[str, tuple[str, str, str | None]] = {}
        self._approved: dict[tuple[str, str], str | None] = {}

    def shown(
        self, tool_use_id: str, dag: DagFile, state: str | None, target: str = ""
    ) -> str | None:
        """Record the state shown on the card (first call wins) and return it.

        ``target`` identifies where the file goes (the card's target text, which includes the team folder),
        so an approval for one folder cannot write to another.
        """
        with self._lock:
            entry = self._shown.get(tool_use_id)
            if entry is None or entry[:2] != (
                f"{target}\x00{dag.file_name}",
                dag.sha256_hex,
            ):
                while len(self._shown) >= self.MAX_ENTRIES:
                    self._shown.pop(next(iter(self._shown)))
                entry = (f"{target}\x00{dag.file_name}", dag.sha256_hex, state)
                self._shown[tool_use_id] = entry
            return entry[2]

    def forget(self, tool_use_id: str) -> None:
        with self._lock:
            self._shown.pop(tool_use_id, None)

    def approve(self, tool_use_id: str) -> None:
        with self._lock:
            name, sha, state = self._shown.pop(tool_use_id)
            while len(self._approved) >= self.MAX_ENTRIES:
                self._approved.pop(next(iter(self._approved)))
            self._approved[(name, sha)] = state

    def take(self, dag: DagFile, target: str = "") -> tuple[bool, str | None]:
        """Return (approved, approved state) for this exact file, content and target, consuming it."""
        with self._lock:
            key = (f"{target}\x00{dag.file_name}", dag.sha256_hex)
            if key not in self._approved:
                return False, None
            return True, self._approved.pop(key)


# For callers that build the hook and tools separately (tests). Sessions pass their own instance.
DEFAULT_APPROVALS = ApprovedDeploys()


def local_target(directory: str) -> DeployTarget:
    root = Path(directory).resolve()

    def path_for(name: str) -> Path:
        path = (root / name).resolve()
        if path.parent != root:
            raise DagDeployError("file must stay in the DAG folder")
        return path

    def state(name: str) -> str | None:
        path = root / name
        if path.is_symlink():
            raise DagDeployError("refusing to replace a symbolic link")
        path = path_for(name)
        if not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write(dag: DagFile, expected: str | None) -> dict[str, Any]:
        path = path_for(dag.file_name)
        if state(dag.file_name) != expected:
            raise _changed_since_approval(dag.file_name)
        fd, tmp = tempfile.mkstemp(dir=root, prefix=".upload-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(dag.data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)  # atomic: the DAG processor never sees a partial file
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {
            "location": f"dags/authored/{dag.file_name}",
            "sha256": dag.sha256_hex,
            "bytes": len(dag.data),
        }

    return DeployTarget(
        describe=lambda name: f"local DAG folder: dags/authored/{name}",
        state=state,
        write=write,
    )


def s3_target(
    s3_client, bucket: str, dag_prefix: str, account: str | None
) -> DeployTarget:
    prefix = dag_prefix.strip("/")
    owner = {"ExpectedBucketOwner": account} if account else {}

    def key_for(name: str) -> str:
        return f"{prefix}/{name}" if prefix else name

    def state(name: str) -> str | None:
        try:
            return s3_client.head_object(Bucket=bucket, Key=key_for(name), **owner)[
                "ETag"
            ]
        except s3_client.exceptions.ClientError as err:
            if err.response.get("Error", {}).get("Code") in (
                "404",
                "NoSuchKey",
                "NotFound",
            ):
                return None
            raise

    def write(dag: DagFile, expected: str | None) -> dict[str, Any]:
        # Conditional write against the state the user approved: fail instead of clobbering a change.
        condition = {"IfMatch": expected} if expected else {"IfNoneMatch": "*"}
        try:
            response = s3_client.put_object(
                Bucket=bucket,
                Key=key_for(dag.file_name),
                Body=dag.data,
                ContentType="text/x-python",
                ChecksumSHA256=base64.b64encode(bytes.fromhex(dag.sha256_hex)).decode(),
                **condition,
                **owner,
            )
        except s3_client.exceptions.ClientError as err:
            if err.response.get("Error", {}).get("Code") in (
                "PreconditionFailed",
                "ConditionalRequestConflict",
                "412",
                "409",
            ):
                raise _changed_since_approval(dag.file_name) from err
            raise
        return {
            "location": f"s3://{bucket}/{key_for(dag.file_name)}",
            "version_id": response.get("VersionId"),
            "sha256": dag.sha256_hex,
            "bytes": len(dag.data),
        }

    return DeployTarget(
        describe=lambda name: f"s3://{bucket}/{key_for(name)}",
        state=state,
        write=write,
    )
