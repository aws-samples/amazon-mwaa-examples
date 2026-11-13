# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Plugin settings, read from the Airflow configuration section [mwaa_agent].

On Amazon MWAA, set them as Airflow configuration options, for example
``mwaa_agent.runtime_arn``. They are not read from Airflow Variables or
Connections on purpose: users who can edit those should not be able to
re-point the agent.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

from airflow.configuration import conf

SECTION = "mwaa_agent"
DAG_DEPLOY_MODES = ("s3_with_approval",)  # future: "pull_request"


class ConfigError(RuntimeError):
    """The plugin is not configured correctly."""


@dataclass(frozen=True)
class Settings:
    runtime_arn: str | None
    environment_name: str
    region: str
    dag_deploy_mode: str
    local_agent_url: str | None
    local_agent_token: str | None
    read_timeout_seconds: int


def _get(key: str, default: str | None = None) -> str | None:
    value = conf.get(SECTION, key, fallback=None)
    return value.strip() if isinstance(value, str) and value.strip() else default


def load_settings() -> Settings:
    """Read and validate settings. Raises ConfigError with an actionable message."""
    environment_name = _get("environment_name") or os.environ.get("AIRFLOW_ENV_NAME")
    if not environment_name:
        raise ConfigError(
            "set mwaa_agent.environment_name to the MWAA environment name"
        )
    region = (
        _get("region")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
    )
    if not region:
        raise ConfigError("set mwaa_agent.region to the environment's AWS Region")

    dag_deploy_mode = _get("dag_deploy_mode", "s3_with_approval")
    if dag_deploy_mode not in DAG_DEPLOY_MODES:
        raise ConfigError(
            f"mwaa_agent.dag_deploy_mode must be one of {DAG_DEPLOY_MODES}"
        )

    # Development only: talk to an agent on this machine or in the same Docker Compose network
    # (a single-label service name such as "mwaa-agent") instead of AgentCore Runtime.
    local_agent_url = _get("local_agent_url")
    if local_agent_url:
        parsed = urlparse(local_agent_url)
        try:
            port = parsed.port
        except ValueError as err:
            raise ConfigError("mwaa_agent.local_agent_url has an invalid port") from err
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("127.0.0.1", "localhost", "mwaa-agent")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or port is None
            or not 1 <= port <= 65535
        ):
            raise ConfigError(
                "mwaa_agent.local_agent_url must be http://127.0.0.1:<port>, http://localhost:<port>, "
                "or http://mwaa-agent:<port>, with no credentials, path, query, or fragment"
            )

    local_agent_token = _get("local_agent_token")
    if local_agent_url and (
        not local_agent_token
        or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", local_agent_token)
    ):
        raise ConfigError(
            "mwaa_agent.local_agent_token must be a 32-128 character URL-safe secret"
        )
    if local_agent_token and not local_agent_url:
        raise ConfigError(
            "mwaa_agent.local_agent_token is only valid with local_agent_url"
        )

    runtime_arn = _get("runtime_arn")
    if not runtime_arn and not local_agent_url:
        raise ConfigError("set mwaa_agent.runtime_arn to the AgentCore Runtime ARN")
    if runtime_arn and not re.fullmatch(
        r"arn:aws(?:-us-gov|-cn|-iso|-iso-b)?:bedrock-agentcore:[a-z0-9-]+:\d{12}:runtime/[A-Za-z0-9_-]+",
        runtime_arn,
    ):
        raise ConfigError("mwaa_agent.runtime_arn is not an AgentCore Runtime ARN")

    try:
        read_timeout = int(_get("read_timeout_seconds", "300"))
    except ValueError as err:
        raise ConfigError("mwaa_agent.read_timeout_seconds must be an integer") from err
    if not 10 <= read_timeout <= 900:
        raise ConfigError("mwaa_agent.read_timeout_seconds must be from 10 to 900")

    return Settings(
        runtime_arn=runtime_arn,
        environment_name=environment_name,
        region=region,
        dag_deploy_mode=dag_deploy_mode,
        local_agent_url=local_agent_url,
        local_agent_token=local_agent_token,
        read_timeout_seconds=read_timeout,
    )
