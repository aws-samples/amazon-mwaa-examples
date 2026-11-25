# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Read-only access to the Python files in a DAG folder.

The agent needs this for DAGs that fail to import (Airflow serves no source for them) and for scanning a
folder before an Airflow upgrade. Which folder a user may read is decided in tools.py; this module only
keeps every path inside that folder and bounds what it returns.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Larger than almost any DAG file, and small enough that a whole file fits in one tool result.
MAX_READ_BYTES = 96 * 1024
MAX_LIST_ENTRIES = 500
# How many entries a listing looks at, .py or not, before it stops and reports a truncated result.
MAX_LIST_SCANNED = 10_000
MAX_PATH_DEPTH = 8
_SEGMENT = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}$")
# Folders Airflow and editors create that never hold DAG sources the user wrote.
_SKIPPED_DIRS = frozenset({"__pycache__"})


class DagFileError(Exception):
    """The folder or file cannot be read. The message is safe to show to the model and user."""


def validate_relative_path(path: Any) -> str:
    """A relative path to a .py file inside the folder: plain segments, no '..', no leading '/'."""
    if not isinstance(path, str) or not path.endswith(".py"):
        raise DagFileError(
            "path must be a .py file relative to the DAG folder, such as 'etl/orders.py'"
        )
    parts = path.split("/")
    if len(parts) > MAX_PATH_DEPTH or not all(_SEGMENT.match(p) for p in parts):
        raise DagFileError(
            "path must be relative to the DAG folder, with plain names (letters, digits, '_', '-', '.'), "
            f"no '..', and at most {MAX_PATH_DEPTH} levels"
        )
    if any(p.startswith(".") or p in _SKIPPED_DIRS for p in parts):
        raise DagFileError("hidden files and folders are not readable")
    return path


def _listable(relative: str) -> bool:
    """Lists show only files that read() accepts."""
    try:
        validate_relative_path(relative)
    except DagFileError:
        return False
    return True


@dataclass(frozen=True)
class SourceFile:
    path: str
    content: str
    size: int  # of the whole file, also when only part of it was read
    truncated: bool
    sha256: str | None  # of the whole file; None when only part of it was read


@dataclass(frozen=True)
class DagFolder:
    """A readable DAG folder. ``describe`` names it for the user (s3://... or the local folder)."""

    describe: str
    list_files: Callable[[], tuple[list[dict[str, Any]], bool]]
    read: Callable[[str], SourceFile]


def _decode(path: str, data: bytes, total_size: int | None = None) -> SourceFile:
    """``data`` holds up to MAX_READ_BYTES + 1 bytes; ``total_size`` is the file size when known."""
    size = max(total_size or 0, len(data))
    truncated = size > MAX_READ_BYTES
    return SourceFile(
        path=path,
        content=data[:MAX_READ_BYTES].decode("utf-8", errors="replace"),
        size=size,
        truncated=truncated,
        sha256=None if truncated else hashlib.sha256(data).hexdigest(),
    )


def local_folder(directory: str, label: str = "dags/authored") -> DagFolder:
    root = Path(directory).resolve()

    def resolve(path: str) -> Path:
        relative = validate_relative_path(path)
        candidate = root / relative
        # Refuse any symbolic link on the way, then confirm the resolved file is still inside the folder.
        probe = candidate
        while probe != root:
            if probe.is_symlink():
                raise DagFileError("symbolic links are not readable")
            probe = probe.parent
        resolved = candidate.resolve()
        if not resolved.is_relative_to(root):
            raise DagFileError("path must stay inside the DAG folder")
        return resolved

    def list_files() -> tuple[list[dict[str, Any]], bool]:
        entries: list[dict[str, Any]] = []
        scanned = 0
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs if not d.startswith(".") and d not in _SKIPPED_DIRS
            )
            for name in sorted(files):
                scanned += 1
                if scanned > MAX_LIST_SCANNED:
                    return entries, True
                full = Path(current) / name
                if full.is_symlink() or not _listable(
                    full.relative_to(root).as_posix()
                ):
                    continue
                if len(entries) >= MAX_LIST_ENTRIES:
                    return entries, True
                entries.append(
                    {
                        "path": full.relative_to(root).as_posix(),
                        "bytes": full.stat().st_size,
                    }
                )
        return entries, False

    def read(path: str) -> SourceFile:
        resolved = resolve(path)
        if not resolved.is_file():
            raise DagFileError(f"{path} does not exist in {label}")
        with resolved.open("rb") as handle:
            data = handle.read(MAX_READ_BYTES + 1)
            total = os.fstat(handle.fileno()).st_size
        return _decode(path, data, total)

    return DagFolder(describe=label, list_files=list_files, read=read)


def s3_folder(s3_client, bucket: str, prefix: str, account: str | None) -> DagFolder:
    prefix = prefix.strip("/")
    if not prefix:
        # The bucket root also holds requirements, plugins and the startup script.
        raise DagFileError("the DAG folder is not configured")
    owner = {"ExpectedBucketOwner": account} if account else {}

    def list_files() -> tuple[list[dict[str, Any]], bool]:
        entries: list[dict[str, Any]] = []
        scanned = 0
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=bucket,
            Prefix=f"{prefix}/",
            PaginationConfig={"MaxItems": MAX_LIST_SCANNED + 1},
            **owner,
        )
        for page in pages:
            for item in page.get("Contents", []) or []:
                scanned += 1
                if scanned > MAX_LIST_SCANNED:
                    return entries, True
                relative = str(item.get("Key", ""))[len(prefix) + 1 :]
                if not _listable(relative):
                    continue
                if len(entries) >= MAX_LIST_ENTRIES:
                    return entries, True
                entries.append({"path": relative, "bytes": int(item.get("Size", 0))})
        return entries, False

    def read(path: str) -> SourceFile:
        key = f"{prefix}/{validate_relative_path(path)}"
        try:
            response = s3_client.get_object(
                Bucket=bucket, Key=key, Range=f"bytes=0-{MAX_READ_BYTES}", **owner
            )
        except s3_client.exceptions.ClientError as err:
            code = err.response.get("Error", {}).get("Code")
            if code == "InvalidRange":
                # S3 refuses any range on an empty object, such as an empty __init__.py.
                return _decode(path, b"", 0)
            if code in ("NoSuchKey", "404"):
                raise DagFileError(
                    f"{path} does not exist in s3://{bucket}/{prefix}/"
                ) from err
            raise
        body = response["Body"]
        try:
            data = body.read(MAX_READ_BYTES + 1)
        finally:
            body.close()
        # A ranged GET returns at most the requested bytes; Content-Range carries the real size.
        return _decode(path, data, _content_range_total(response.get("ContentRange")))

    return DagFolder(
        describe=f"s3://{bucket}/{prefix}/", list_files=list_files, read=read
    )


def _content_range_total(header: Any) -> int | None:
    """The total size from a Content-Range header such as 'bytes 0-262144/900000'."""
    if not isinstance(header, str) or "/" not in header:
        return None
    total = header.rsplit("/", 1)[1]
    return int(total) if total.isdigit() else None
