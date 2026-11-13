# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Deterministic tool policy for the MWAA UI agent.

The model never decides its own authority. This module uses explicit API and
route allowlists, validates mutation schemas, and marks every mutation for
human approval. IAM remains the final AWS boundary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

TIER_READ = "read"
TIER_OPERATE = "operate"
TIERS = (TIER_READ, TIER_OPERATE)

# A reviewed operation allowlist. Prefix-based rules are unsafe: some Get*/
# Describe* APIs mint credentials, return secrets, claim work, or start jobs.
ALLOWED_AWS_OPERATIONS = frozenset(
    {
        ("mwaa", "GetEnvironment"),
        ("logs", "DescribeLogStreams"),
        ("logs", "GetLogEvents"),
        ("logs", "FilterLogEvents"),
        ("logs", "StartQuery"),
        ("logs", "GetQueryResults"),
        ("s3", "GetObject"),
        ("s3", "GetObjectVersion"),
        ("s3", "HeadObject"),
        ("s3", "ListObjectsV2"),
        ("s3", "GetBucketVersioning"),
        ("cloudwatch", "GetMetricData"),
        ("cloudwatch", "ListMetrics"),
        ("cloudwatch", "DescribeAlarms"),
        ("sts", "GetCallerIdentity"),
        ("iam", "GetRole"),
        ("iam", "ListAttachedRolePolicies"),
        ("iam", "ListRolePolicies"),
        ("iam", "GetRolePolicy"),
        ("iam", "SimulatePrincipalPolicy"),
        ("iam", "GetPolicy"),
        ("iam", "GetPolicyVersion"),
        ("glue", "GetJob"),
        ("glue", "GetJobRun"),
        ("glue", "GetJobRuns"),
        ("emr", "DescribeCluster"),
        ("emr", "DescribeStep"),
        ("emr", "ListSteps"),
        ("emr-serverless", "GetApplication"),
        ("emr-serverless", "GetJobRun"),
        ("athena", "GetQueryExecution"),
        ("redshift-data", "DescribeStatement"),
        ("stepfunctions", "DescribeExecution"),
        ("batch", "DescribeJobs"),
        ("ecs", "DescribeTasks"),
        ("sagemaker", "DescribeTrainingJob"),
        ("sagemaker", "DescribeProcessingJob"),
        ("ec2", "DescribeVpcEndpoints"),
        ("ec2", "DescribeSecurityGroups"),
        ("ec2", "DescribeSubnets"),
        ("ec2", "DescribeRouteTables"),
        ("ec2", "DescribeNetworkAcls"),
    }
)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    needs_approval: bool = False


def check_aws(service: str, operation: str) -> Decision:
    """Require an exact service and canonical PascalCase operation."""
    if (service, operation) not in ALLOWED_AWS_OPERATIONS:
        return Decision(
            False,
            f"{service}:{operation} is not in the agent's reviewed read-only API allowlist",
        )
    return Decision(True)


# ---------------------------------------------------------------------------
# Airflow REST API policy
# ---------------------------------------------------------------------------

DENIED_AIRFLOW_PREFIXES = (
    "/connections",
    "/variables",
    "/config",
    "/users",
    "/roles",
    "/permissions",
    "/auth",
    "/backfills",
)
# Unauthenticated status routes. /plugins and /providers are left out: on MWAA the agent calls Airflow as
# the User role, which cannot read them, so they would work locally (where the agent is admin) but not on MWAA.
GLOBAL_SAFE_GETS = ("/version", "/monitor/health", "/health")
GLOBAL_SCOPED_GETS = ("/dags", "/importErrors")
_DAG_ID = r"[A-Za-z0-9_.-]{1,250}"
_SEGMENT = r"[^/%\\?#\x00-\x1f]{1,250}"
_DAG_PATH = re.compile(rf"^/(?:dags|dagSources)/(?P<dag_id>{_DAG_ID})(?P<rest>/.*)?$")
_MUTATIONS = (
    ("POST", re.compile(r"^/dagRuns$"), "trigger a DAG run", None),
    ("PATCH", re.compile(r"^$"), "pause or unpause the DAG", None),
    (
        "POST",
        re.compile(r"^/clearTaskInstances$"),
        "clear task instances so they run again",
        "can_edit_task_instances",
    ),
    (
        "PATCH",
        re.compile(rf"^/dagRuns/{_SEGMENT}$"),
        "set the state of a DAG run",
        "can_edit_runs",
    ),
    (
        "PATCH",
        re.compile(rf"^/dagRuns/{_SEGMENT}/taskInstances/{_SEGMENT}(?:/-?\d+)?$"),
        "set the state of a task instance",
        "can_edit_task_instances",
    ),
)
_CAPABILITY_LABELS = {
    "can_edit_task_instances": "edit task instances",
    "can_edit_runs": "edit DAG runs",
}
MAX_BODY_BYTES = 64 * 1024
MAX_QUERY_BYTES = 8 * 1024
MAX_JSON_DEPTH = 12
MAX_QUERY_ITEMS = 20


@dataclass
class AccessScope:
    tier: str = TIER_READ
    all_dags_readable: bool = False
    readable_dags: frozenset[str] = field(default_factory=frozenset)
    runnable_dags: frozenset[str] = field(default_factory=frozenset)
    # Writing DAG files runs code on workers, so it needs more than the operate tier (see plugin access.py).
    can_deploy_dags: bool = False
    # Airflow's separate PUT permissions on task instances and on DAG runs.
    can_edit_task_instances: bool = False
    can_edit_runs: bool = False
    # The plugin sent only part of a very long DAG list; the page's DAG is always included.
    dag_lists_truncated: bool = False
    # Airflow multi-team mode, and the teams the user belongs to.
    multi_team: bool = False
    teams: frozenset[str] = field(default_factory=frozenset)

    def can_read(self, dag_id: str) -> bool:
        return self.all_dags_readable or dag_id in self.readable_dags

    def can_run(self, dag_id: str) -> bool:
        return self.tier == TIER_OPERATE and dag_id in self.runnable_dags


def _json_depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        return depth
    if isinstance(value, dict):
        return (
            max((_json_depth(k, depth + 1) for k in value), default=depth + 1)
            if not value
            else max(
                [_json_depth(k, depth + 1) for k in value]
                + [_json_depth(v, depth + 1) for v in value.values()]
            )
        )
    if isinstance(value, (list, tuple)):
        return max((_json_depth(v, depth + 1) for v in value), default=depth + 1)
    return depth


def _bounded_json(value: Any, max_bytes: int, label: str) -> str | None:
    try:
        encoded = json.dumps(value, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        return f"{label} must be JSON serializable"
    if len(encoded) > max_bytes:
        return f"{label} exceeds {max_bytes} bytes"
    if _json_depth(value) > MAX_JSON_DEPTH:
        return f"{label} exceeds the maximum nesting depth of {MAX_JSON_DEPTH}"
    return None


def _validate_query(query: dict | None) -> str | None:
    if query is None:
        return None
    if not isinstance(query, dict) or len(query) > MAX_QUERY_ITEMS:
        return f"query must be an object with at most {MAX_QUERY_ITEMS} fields"
    error = _bounded_json(query, MAX_QUERY_BYTES, "query")
    if error:
        return error
    for key, value in query.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", key):
            return "query contains an invalid key"
        if key.lower() in ("limit", "page_limit") and (
            not isinstance(value, int)
            or isinstance(value, bool)
            or not 1 <= value <= 1000
        ):
            return f"query field '{key}' must be an integer from 1 to 1000"
    return None


def _exact_keys(
    body: dict, allowed: set[str], required: set[str] = frozenset()
) -> str | None:
    extra = set(body) - allowed
    missing = required - set(body)
    if extra:
        return f"request body contains unsupported fields: {', '.join(sorted(extra))}"
    if missing:
        return f"request body is missing fields: {', '.join(sorted(missing))}"
    return None


def _validate_mutation(method: str, rest: str, body: dict | None) -> str | None:
    if not isinstance(body, dict):
        return "a JSON object body is required"
    error = _bounded_json(body, MAX_BODY_BYTES, "request body")
    if error:
        return error
    if method == "PATCH" and rest == "":
        error = _exact_keys(body, {"is_paused"}, {"is_paused"})
        if error:
            return error
        if not isinstance(body["is_paused"], bool):
            return "is_paused must be true or false"
    elif method == "POST" and rest == "/dagRuns":
        error = _exact_keys(body, {"dag_run_id", "logical_date", "conf", "note"})
        if error:
            return error
        if "dag_run_id" in body and (
            not isinstance(body["dag_run_id"], str)
            or not re.fullmatch(_SEGMENT, body["dag_run_id"])
        ):
            return "dag_run_id is invalid"
        if (
            "logical_date" in body
            and body["logical_date"] is not None
            and not isinstance(body["logical_date"], str)
        ):
            return "logical_date must be a string or null"
        if "conf" in body and not isinstance(body["conf"], dict):
            return "conf must be an object"
    elif method == "POST" and rest == "/clearTaskInstances":
        # The fields of Airflow 3's ClearTaskInstancesBody (extra="forbid"), minus date ranges. dry_run must
        # be explicit: Airflow defaults it to true, so a clear without it silently changes nothing.
        allowed = {
            "dag_run_id",
            "task_ids",
            "dry_run",
            "only_failed",
            "only_running",
            "reset_dag_runs",
            "include_upstream",
            "include_downstream",
            "start_date",
            "end_date",
        }
        error = _exact_keys(body, allowed, {"dag_run_id", "task_ids", "dry_run"})
        if error:
            return error
        # With dag_run_id null, Airflow falls back to the date range, which by default covers every run.
        if not isinstance(body["dag_run_id"], str) or not re.fullmatch(
            _SEGMENT, body["dag_run_id"]
        ):
            return "dag_run_id must name one DAG run"
        for key in ("start_date", "end_date"):
            if key in body and body[key] is not None:
                return f"{key} is not supported; clear tasks of one DAG run at a time"
        if (
            not isinstance(body["task_ids"], list)
            or not 1 <= len(body["task_ids"]) <= 500
        ):
            return "task_ids must contain 1 to 500 task ids"
        if not all(
            isinstance(v, str) and re.fullmatch(_SEGMENT, v) for v in body["task_ids"]
        ):
            return "task_ids contains an invalid task id"
        for key in (
            "dry_run",
            "only_failed",
            "only_running",
            "reset_dag_runs",
            "include_upstream",
            "include_downstream",
        ):
            if key in body and not isinstance(body[key], bool):
                return f"{key} must be true or false"
    elif method == "PATCH" and "/dagRuns/" in rest and "/taskInstances/" not in rest:
        error = _exact_keys(body, {"state", "note"}, {"state"})
        if error:
            return error
        if body["state"] not in ("success", "failed"):
            return "run state must be 'success' or 'failed'"
    elif method == "PATCH" and "/taskInstances/" in rest:
        error = _exact_keys(body, {"new_state"}, {"new_state"})
        if error:
            return error
        if body["new_state"] not in ("success", "failed"):
            return "task state must be 'success' or 'failed'"
    return None


def _scope_denial(scope: AccessScope, reason: str) -> str:
    if scope.dag_lists_truncated:
        return (
            f"{reason}, or the DAG is beyond the part of the user's very long DAG list that the plugin "
            "sends; ask the user to open this DAG's page in Airflow and ask again"
        )
    return reason


def check_airflow(
    scope: AccessScope,
    method: str,
    path: str,
    body: dict | None = None,
    query: dict | None = None,
) -> Decision:
    method = method.upper()
    if (
        not path.startswith("/")
        or ".." in path
        or "%" in path
        or "\\" in path
        or "//" in path
        or "?" in path
        or "#" in path
        or any(ord(ch) < 32 for ch in path)
    ):
        return Decision(False, "path is not a canonical Airflow API path")
    if path.startswith(DENIED_AIRFLOW_PREFIXES):
        return Decision(
            False,
            f"{path} is blocked: it exposes connections, variables, configuration, or identities",
        )
    query_error = _validate_query(query)
    if query_error:
        return Decision(False, query_error)

    if path.startswith("/dags/~/"):
        return Decision(
            False,
            "cross-DAG ('~') queries are disabled; query one authorized DAG at a time",
        )
    match = _DAG_PATH.match(path)
    if method == "GET":
        if match:
            dag_id = match.group("dag_id")
            if dag_id == "~":
                return Decision(
                    False,
                    "cross-DAG ('~') queries are disabled; query one authorized DAG at a time",
                )
            if scope.can_read(dag_id):
                return Decision(True)
            return Decision(
                False,
                _scope_denial(
                    scope, f"the user does not have read access to DAG '{dag_id}'"
                ),
            )
        if path in GLOBAL_SAFE_GETS:
            return Decision(True)
        if scope.all_dags_readable and any(
            path == root or path.startswith(root + "/") for root in GLOBAL_SCOPED_GETS
        ):
            return Decision(True)
        return Decision(
            False,
            "this global endpoint is not available; query an authorized DAG directly",
        )

    if scope.tier != TIER_OPERATE:
        return Decision(
            False,
            "the user's Airflow role is read-only for this agent; tell them what to change instead",
        )
    if not match or path.startswith("/dagSources"):
        return Decision(False, f"{method} {path} is not an action this agent can take")
    dag_id = match.group("dag_id")
    rest = match.group("rest") or ""
    if not scope.can_run(dag_id):
        return Decision(
            False,
            _scope_denial(
                scope, f"the user cannot trigger or change runs of DAG '{dag_id}'"
            ),
        )
    for verb, pattern, label, capability in _MUTATIONS:
        if verb == method and pattern.fullmatch(rest):
            if capability and not getattr(scope, capability):
                return Decision(
                    False,
                    f"the user's Airflow role cannot {_CAPABILITY_LABELS[capability]}, so the agent "
                    f"cannot {label}; tell them what to change instead",
                )
            error = _validate_mutation(method, rest, body)
            return Decision(not error, error or "", needs_approval=not error)
    return Decision(False, f"{method} {path} is not an action this agent can take")


def describe_mutation(method: str, path: str) -> str:
    match = _DAG_PATH.match(path)
    if not match:
        return f"{method.upper()} {path}"
    rest = match.group("rest") or ""
    for verb, pattern, label, _capability in _MUTATIONS:
        if verb == method.upper() and pattern.fullmatch(rest):
            return f"{label} for DAG '{match.group('dag_id')}'"
    return f"{method.upper()} {path}"
