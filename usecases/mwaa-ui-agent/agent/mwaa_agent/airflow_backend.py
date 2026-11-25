# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Backends for the Airflow REST API.

Production uses MWAA InvokeRestApi. Local development uses one fixed Compose or
loopback Airflow origin, with redirects disabled and bounded responses.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import boto3
from botocore.config import Config

_BOTO_CONFIG = Config(
    retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=60, connect_timeout=10
)
MAX_LOCAL_RESPONSE_BYTES = 1024 * 1024
_ALLOWED_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "webserver"})


class AirflowBackendError(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__(payload.get("message", "Airflow API call failed"))
        self.payload = payload


class MwaaBackend:
    def __init__(self, environment_name: str, region: str) -> None:
        self._environment_name = environment_name
        self._client = boto3.client("mwaa", region_name=region, config=_BOTO_CONFIG)

    def call(
        self, method: str, path: str, query: dict | None, body: dict | None
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "Name": self._environment_name,
            "Path": path,
            "Method": method,
        }
        if query:
            request["QueryParameters"] = query
        if body is not None and method != "GET":
            request["Body"] = body
        response = self._client.invoke_rest_api(**request)
        return {
            "status": response.get("RestApiStatusCode"),
            "response": response.get("RestApiResponse"),
        }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class LocalBackend:
    """Development-only direct Airflow API client."""

    def __init__(self, base_url: str, username: str, password: str) -> None:
        parsed = urllib.parse.urlparse(base_url)
        try:
            port = parsed.port
        except ValueError as err:
            raise ValueError("AIRFLOW_API_BASE_URL has an invalid port") from err
        if (
            parsed.scheme != "http"
            or parsed.hostname not in _ALLOWED_LOCAL_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or port is None
            or not 1 <= port <= 65535
        ):
            raise ValueError(
                "AIRFLOW_API_BASE_URL must be an exact loopback or Compose webserver origin"
            )
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._lock = threading.Lock()
        self._opener = urllib.request.build_opener(_NoRedirect)

    @staticmethod
    def _read_bounded(response) -> bytes:
        data = response.read(MAX_LOCAL_RESPONSE_BYTES + 1)
        if len(data) > MAX_LOCAL_RESPONSE_BYTES:
            raise AirflowBackendError(
                {
                    "error": "ResponseTooLarge",
                    "message": "Airflow API response exceeded 1 MiB",
                }
            )
        return data

    def _login(self) -> str:
        data = json.dumps(
            {"username": self._username, "password": self._password}
        ).encode()
        request = urllib.request.Request(
            f"{self._base}/auth/token",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self._opener.open(request, timeout=30) as response:  # nosec B310 - exact dev-only host allowlist
            payload = json.loads(self._read_bounded(response))
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise AirflowBackendError(
                {
                    "error": "AuthenticationFailed",
                    "message": "Airflow did not return a token",
                }
            )
        return token

    def _request(
        self, method: str, path: str, query: dict | None, body: dict | None, token: str
    ):
        url = f"{self._base}/api/v2{urllib.parse.quote(path, safe='/~:@+-._')}"
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        data = (
            json.dumps(body).encode() if body is not None and method != "GET" else None
        )
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method=method,
        )
        return self._opener.open(request, timeout=60)  # nosec B310 - exact dev-only host allowlist

    def call(
        self, method: str, path: str, query: dict | None, body: dict | None
    ) -> dict[str, Any]:
        with self._lock:
            if self._token is None:
                self._token = self._login()
            token = self._token
        for attempt in (1, 2):
            try:
                with self._request(method, path, query, body, token) as response:
                    raw = self._read_bounded(response).decode("utf-8", errors="replace")
                    status = response.status
                break
            except urllib.error.HTTPError as err:
                if err.code == 401 and attempt == 1:
                    with self._lock:
                        self._token = token = self._login()
                    continue
                raw = err.read(4001).decode("utf-8", errors="replace")
                raise AirflowBackendError(
                    {
                        "error": f"HTTP {err.code}",
                        "status": err.code,
                        "message": raw[:4000],
                    }
                ) from err
        try:
            parsed: Any = json.loads(raw) if raw else None
        except ValueError:
            parsed = raw
        return {"status": status, "response": parsed}


_local_backend: LocalBackend | None = None


def make_backend(environment_name: str, region: str):
    global _local_backend  # pylint: disable=global-statement
    base_url = os.environ.get("AIRFLOW_API_BASE_URL")
    if base_url:
        if _local_backend is None:
            _local_backend = LocalBackend(
                base_url,
                os.environ.get("AIRFLOW_API_USERNAME", "admin"),
                os.environ.get("AIRFLOW_API_PASSWORD", ""),
            )
        return _local_backend
    return MwaaBackend(environment_name, region)
