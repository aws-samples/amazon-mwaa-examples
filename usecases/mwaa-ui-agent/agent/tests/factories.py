# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Request payloads and environment facts shared by the agent test modules."""

from __future__ import annotations


def payload(**overrides):
    ctx = {
        "environment_name": "env1",
        "region": "eu-west-1",
        "airflow_version": "3.1.8",
        "user_id": "1",
        "user_name": "alice",
        "tier": "operate",
        "all_dags_readable": False,
        "readable_dags": ["etl"],
        "runnable_dags": ["etl"],
        "page": {
            "dag_id": "etl",
            "run_id": "manual__2026-01-01T00:00:00+00:00",
            "task_id": "t",
            "map_index": -1,
        },
    }
    ctx.update(overrides.pop("context", {}))
    body = {"type": "message", "text": "why?", "context": ctx}
    body.update(overrides)
    return body


# What RuntimeResources.environment returns for a plain (no teams) MWAA environment.
_ENV_FACTS = {
    "bucket": "env-bucket",
    "execution_role_arn": "arn:aws:iam::111122223333:role/exec",
    "execution_role_name": "exec",
    "account": "111122223333",
    "dag_s3_path": "dags",
    "teams": {},
    "identity_center": False,
}


TEAMS_ENV = {
    "DataEng-TeamA": {"bucket": "acme-airflow", "dag_s3_path": "teams/DataEng-TeamA"},
    "DataEng-TeamB": {"bucket": "acme-airflow", "dag_s3_path": "teams/DataEng-TeamB"},
}
