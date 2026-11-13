# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Agent tools with deterministic policy and resource scoping."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from strands import tool

from . import dag_deploy, dag_files, dag_lint, policy
from .airflow_backend import AirflowBackendError, make_backend
from .context import SessionContext
from .sanitize import clean, redact, scrub

MAX_S3_OBJECT_BYTES = 256 * 1024
MAX_SKILL_FILE_BYTES = 256 * 1024
MAX_AWS_PARAMS_BYTES = 64 * 1024
# A whole DAG file read or lint result, JSON-escaped; above MAX_TOOL_OUTPUT_CHARS, which suits API responses.
MAX_DAG_READ_CHARS = 140_000
_REGION = re.compile(r"^[a-z]{2}(-gov|-iso[a-z]?)?-[a-z]+-\d$")
_PASCAL = re.compile(r"^[A-Z][A-Za-z0-9]+$")
_BOTO_CONFIG = Config(
    retries={"max_attempts": 4, "mode": "adaptive"}, read_timeout=60, connect_timeout=10
)
ContextGetter = Callable[[], SessionContext]


def _to_json(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, (bytes, bytearray)):
            return obj.decode("utf-8", errors="replace")
        return str(obj)

    return json.dumps(scrub(value), default=default, indent=1)


def _client_error(err: Exception) -> str:
    if isinstance(err, ClientError):
        error = err.response.get("Error", {})
        details = {
            k: v
            for k, v in err.response.items()
            if k not in ("Error", "ResponseMetadata")
        }
        out = {"error": error.get("Code"), "message": error.get("Message")}
        if details:
            out["details"] = details
        return clean(_to_json(out))
    return clean(_to_json({"error": type(err).__name__, "message": str(err)}))


def normalize_operation(operation: str) -> str:
    """Normalize snake_case/CLI spelling, while preserving PascalCase for exact allowlist validation."""
    op = operation.strip()
    if _PASCAL.fullmatch(op):
        return op
    return "".join(part.capitalize() for part in re.split(r"[-_]", op) if part)


def _bucket_name(bucket_arn: str) -> str:
    return bucket_arn.split(":::", 1)[-1] if ":::" in bucket_arn else bucket_arn


class RuntimeResources:
    """Resources derived by the runtime itself, never trusted from the request payload."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._policy_cache: dict[tuple[str, str], frozenset[str]] = {}

    def environment(self, ctx: SessionContext) -> dict[str, Any]:
        key = (ctx.region, ctx.environment_name)
        if key not in self._cache:
            response = boto3.client(
                "mwaa", region_name=ctx.region, config=_BOTO_CONFIG
            ).get_environment(Name=ctx.environment_name)
            env = response["Environment"]
            bucket_arn = env.get("SourceBucketArn", "")
            role_arn = env.get("ExecutionRoleArn", "")
            account = role_arn.split(":")[4] if role_arn.count(":") >= 5 else ""
            self._cache[key] = {
                "bucket": _bucket_name(bucket_arn),
                "execution_role_arn": role_arn,
                "execution_role_name": role_arn.rsplit("/", 1)[-1],
                "account": account,
                "dag_s3_path": str(env.get("DagS3Path") or "dags").strip("/"),
                # Airflow 3.3.1 multi-team: {team: {"bucket": ..., "dag_s3_path": ...}}. Empty when off.
                "teams": {
                    str(name): {
                        "bucket": _bucket_name(str(cfg.get("SourceBucketArn", ""))),
                        "dag_s3_path": str(cfg.get("DagS3Path") or "").strip("/"),
                    }
                    for name, cfg in (env.get("Teams") or {}).items()
                    if isinstance(cfg, dict)
                },
                "identity_center": bool(env.get("IdentityCenterConfiguration")),
            }
        return self._cache[key]

    def attached_policies(self, ctx: SessionContext) -> frozenset[str]:
        key = (ctx.region, ctx.environment_name)
        if key not in self._policy_cache:
            env = self.environment(ctx)
            response = boto3.client(
                "iam", region_name=ctx.region, config=_BOTO_CONFIG
            ).list_attached_role_policies(RoleName=env["execution_role_name"])
            self._policy_cache[key] = frozenset(
                p["PolicyArn"] for p in response.get("AttachedPolicies", [])
            )
        return self._policy_cache[key]


_RESOURCES = RuntimeResources()

INVOKE_ACTION = "bedrock-agentcore:InvokeAgentRuntime"
_INVOKER_CHECK_TTL_SECONDS = 300
_invoker_check: dict[tuple[str, str, str], tuple[float, str | None]] = {}
_invoker_lock = threading.Lock()


def own_runtime_arn() -> str | None:
    """This runtime's ARN, from the OpenTelemetry resource attributes AgentCore Runtime sets.

    The bedrock-agentcore SDK reads the same attribute (cloud.resource_id). Endpoint ARNs are reduced to the
    runtime ARN.
    """
    for attr in os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "").split(","):
        key, _, value = attr.strip().partition("=")
        if key == "cloud.resource_id" and ":runtime/" in value:
            return value.split("/runtime-endpoint/")[0]
    return None


def _execution_role_invoke_error(ctx: SessionContext) -> str | None:
    """Why DAG deployment must stay off on MWAA, or None if the execution role cannot invoke this runtime.

    Identity, tier, scope and approvals all arrive in the request. When the MWAA execution role may call
    InvokeAgentRuntime, any DAG task (which runs as that role) can send a request that claims to be an Admin
    and approves its own deploy_dag call, and so plant DAG files. Until requests come through a broker with
    its own role, deployment is refused whenever that role can invoke the runtime. Every failure is a refusal.

    Limit: the simulation sees only the execution role's own policies. A DAG task that assumes another role
    that trusts the execution role, or uses stored credentials, could still invoke the runtime. Keep DAG
    authoring to development and test environments until requests come through a broker.
    """
    blocked = (
        "DAG deployment is blocked on this environment: the MWAA execution role can invoke this agent "
        "runtime, so any DAG could forge a deploy request and approve it. Deploy DAG files through your "
        "usual pipeline, or put an authenticated broker with its own role in front of the runtime"
    )
    runtime_arn = own_runtime_arn()
    if not runtime_arn:
        return (
            "DAG deployment is blocked: the runtime cannot determine its own ARN, so it cannot check "
            "whether the MWAA execution role can invoke it"
        )
    try:
        role_arn = _RESOURCES.environment(ctx)["execution_role_arn"]
    except (ClientError, BotoCoreError, KeyError):
        return blocked
    key = (ctx.region, role_arn, runtime_arn)
    now = time.monotonic()
    with _invoker_lock:
        cached = _invoker_check.get(key)
        if cached and now - cached[0] < _INVOKER_CHECK_TTL_SECONDS:
            return cached[1]
    try:
        results = (
            boto3.client("iam", region_name=ctx.region, config=_BOTO_CONFIG)
            .simulate_principal_policy(
                PolicySourceArn=role_arn,
                ActionNames=[INVOKE_ACTION],
                ResourceArns=[runtime_arn, f"{runtime_arn}/runtime-endpoint/DEFAULT"],
            )
            .get("EvaluationResults", [])
        )
    except (ClientError, BotoCoreError):
        return blocked  # not cached, so a transient failure does not block for the whole TTL
    decisions = [r.get("EvalDecision") for r in results] + [
        r.get("EvalResourceDecision")
        for result in results
        for r in result.get("ResourceSpecificResults", [])
    ]
    error = blocked if not results or "allowed" in decisions else None
    with _invoker_lock:
        _invoker_check[key] = (now, error)
    return error


def deploy_block_reason(ctx: SessionContext) -> str | None:
    """Why deploy_dag cannot run on this runtime, independent of the user. None when it is available."""
    if not dag_deploy.deploy_enabled():
        return "DAG deployment is disabled on this agent runtime (ENABLE_DAG_DEPLOY is not true)"
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        # Local runner: the workers are not on the agent network and never get LOCAL_INVOCATION_TOKEN.
        return None
    return _execution_role_invoke_error(ctx)


# Airflow configuration sections whose values are operational tuning, not credentials. Other options are
# listed by name only, because values such as secrets.backend_kwargs can hold sensitive data.
_SAFE_CONFIG_SECTIONS = (
    "core.",
    "scheduler.",
    "celery.",
    "dag_processor.",
    "webserver.",
    "api.",
)


def environment_profile(ctx: SessionContext) -> dict[str, Any]:
    """Facts about where the agent runs, for the system prompt. Built by the runtime, never from the payload."""
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        return {
            "deployment": "Local MWAA runner (amazon-mwaa-docker-images) on Docker Compose, not Amazon MWAA",
            "airflow_version": ctx.airflow_version,
            "dags_folder": "/usr/local/airflow/dags"
            + (
                " (the agent deploys to its authored/ subfolder)"
                if dag_deploy.deploy_enabled()
                else ""
            ),
            "task_logs": (
                "Written to the local log folder and served by the Airflow API. There is no CloudWatch, so "
                "the airflow_api logs route is the only source. 'Could not read served logs' means the "
                "worker that ran the task is gone and its log was not kept."
            ),
            "aws_tools": "Disabled locally: aws_api cannot reach AWS, so do not try AWS calls here.",
            "workers": "Containers; their hostnames change when they are recreated.",
        }
    try:
        env = boto3.client(
            "mwaa", region_name=ctx.region, config=_BOTO_CONFIG
        ).get_environment(Name=ctx.environment_name)["Environment"]
    except (ClientError, BotoCoreError) as err:
        return {"deployment": "Amazon MWAA", "profile_error": type(err).__name__}
    logging_cfg = {
        name.removesuffix("Logs"): {
            "enabled": cfg.get("Enabled", False),
            "level": cfg.get("LogLevel"),
            "log_group": str(cfg.get("CloudWatchLogGroupArn", ""))
            .split(":log-group:")[-1]
            .removesuffix(":*")
            or None,
        }
        for name, cfg in (env.get("LoggingConfiguration") or {}).items()
    }
    options = env.get("AirflowConfigurationOptions") or {}
    last_update = env.get("LastUpdate") or {}
    return scrub(
        {
            "deployment": "Amazon MWAA (provisioned), Celery executor",
            "airflow_version": env.get("AirflowVersion"),
            "status": env.get("Status"),
            "last_update": {
                "status": last_update.get("Status"),
                "error": (last_update.get("Error") or {}).get("ErrorMessage"),
            },
            "environment_class": env.get("EnvironmentClass"),
            "schedulers": env.get("Schedulers"),
            "workers": {"min": env.get("MinWorkers"), "max": env.get("MaxWorkers")},
            "webserver_access_mode": env.get("WebserverAccessMode"),
            "source_bucket": str(env.get("SourceBucketArn", "")).split(":::")[-1],
            "dag_s3_path": env.get("DagS3Path"),
            "requirements_s3_path": env.get("RequirementsS3Path"),
            "plugins_s3_path": env.get("PluginsS3Path"),
            "startup_script_s3_path": env.get("StartupScriptS3Path"),
            "execution_role": str(env.get("ExecutionRoleArn", "")).rsplit("/", 1)[-1],
            "customer_managed_kms_key": bool(env.get("KmsKey")),
            "logging": logging_cfg,
            "task_log_stream_format": "dag_id=<dag>/run_id=<run>/task_id=<task>/attempt=<n>.log",
            "identity_center": bool(env.get("IdentityCenterConfiguration")),
            "teams": (
                {
                    # Only the user's own teams: other teams' names and folders are not theirs to see.
                    "count": len(env["Teams"]),
                    "user_teams": sorted(set(env["Teams"]) & ctx.scope.teams),
                    "dag_folders": {
                        name: f"s3://{_bucket_name(str(cfg.get('SourceBucketArn', '')))}/"
                        f"{str(cfg.get('DagS3Path') or '').strip('/')}"
                        for name, cfg in sorted(env["Teams"].items())
                        if isinstance(cfg, dict) and name in ctx.scope.teams
                    },
                    "worker_paths": "global DAGs: /usr/local/airflow/dags/global-dags (bundle shared_dags); "
                    "team DAGs: /usr/local/airflow/dags/per-team-dags/<team> (bundle team_<team>)",
                }
                if env.get("Teams")
                else None
            ),
            "airflow_configuration_options": {
                key: (
                    value if key.startswith(_SAFE_CONFIG_SECTIONS) else "(value hidden)"
                )
                for key, value in sorted(options.items())
            },
            "deploy_dag_available": deploy_block_reason(ctx) is None,
        }
    )


def deploy_target(
    ctx: SessionContext, team: str | None = None
) -> dag_deploy.DeployTarget:
    """The DAG folder for this runtime and team. Derived by the runtime, never from the request payload.

    Without a team this is the environment's DagS3Path; in multi-team mode those DAGs form the shared_dags
    bundle, which every team sees. With a team it is that team's own DagS3Path from GetEnvironment.Teams.
    """
    local_dir = os.environ.get("MWAA_AGENT_LOCAL_DAGS_DIR")
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        if team:
            raise dag_deploy.DagDeployError(
                "the local runner has no team DAG folders; deploy without a team"
            )
        if not local_dir:
            raise dag_deploy.DagDeployError(
                "local DAG deployment needs MWAA_AGENT_LOCAL_DAGS_DIR"
            )
        return dag_deploy.local_target(local_dir)
    env = _RESOURCES.environment(ctx)
    s3 = boto3.client("s3", region_name=ctx.region, config=_BOTO_CONFIG)
    if team:
        cfg = env["teams"][team]
        return dag_deploy.s3_target(
            s3, cfg["bucket"], cfg["dag_s3_path"], env["account"] or None
        )
    return dag_deploy.s3_target(
        s3, env["bucket"], env["dag_s3_path"], env["account"] or None
    )


def readable_dag_folder(ctx: SessionContext, team: Any = None) -> dag_files.DagFolder:
    """The DAG folder this user may read through read_dag_file and lint_dag, chosen by the runtime.

    The same rules as aws_api's S3 reads: the environment's DAG folder needs read access to every DAG,
    because it holds every DAG's source; on environments with teams only the user's own team folders are
    readable. Locally, the agent's own folder (dags/authored) is readable.
    """
    if team in ("", None):
        team = None
    elif not isinstance(team, str):
        raise dag_files.DagFileError("team must be a team name")
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        local_dir = os.environ.get("MWAA_AGENT_LOCAL_DAGS_DIR")
        if team:
            raise dag_files.DagFileError("the local runner has no team DAG folders")
        if not local_dir:
            raise dag_files.DagFileError(
                "no readable DAG folder is configured (MWAA_AGENT_LOCAL_DAGS_DIR)"
            )
        if not _reads_all_dags(ctx):
            raise dag_files.DagFileError(
                "reading the DAG folder needs read access to all DAGs"
            )
        return dag_files.local_folder(local_dir)
    env = _RESOURCES.environment(ctx)
    s3 = boto3.client("s3", region_name=ctx.region, config=_BOTO_CONFIG)
    account = env["account"] or None
    if team is not None:
        folders = _team_folders(ctx)
        if team not in folders:
            # One message for "no such team" and "not your team", so the reply does not reveal team names.
            raise dag_files.DagFileError(
                f"{team!r} is not one of the user's teams with a DAG folder"
            )
        cfg = folders[team]
        return dag_files.s3_folder(s3, cfg["bucket"], cfg["dag_s3_path"], account)
    if not _reads_all_dags(ctx):
        hint = (
            "pass team= one of the user's teams to read that team's folder"
            if _team_folders(ctx)
            else "read one DAG's source with airflow_api GET /dagSources/<dag_id> instead"
        )
        raise dag_files.DagFileError(
            "reading the environment's DAG folder needs read access to all DAGs, because it holds every "
            f"DAG's source; {hint}"
        )
    return dag_files.s3_folder(s3, env["bucket"], env["dag_s3_path"], account)


def check_deploy_team(ctx: SessionContext, team: Any) -> str | None:
    """Validate the team for an upload; returns the team (or None for the global folder)."""
    if team in (None, ""):
        team = None
    elif not isinstance(team, str):
        raise dag_deploy.DagDeployError("team must be a team name")
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        env_teams: dict[str, Any] = {}
    else:
        env_teams = _RESOURCES.environment(ctx).get("teams") or {}
    if team is None:
        if env_teams or ctx.scope.multi_team:
            names = ", ".join(sorted(ctx.scope.teams & set(env_teams))) or "none"
            raise dag_deploy.DagDeployError(
                "this environment uses teams, and a DAG in the global folder (the shared_dags bundle) is "
                "visible to every team, so the agent deploys only into a team folder. Pass team= one of "
                f"the user's teams: {names}"
            )
        return None
    if team not in env_teams:
        raise dag_deploy.DagDeployError(f"{team!r} is not a team on this environment")
    if team not in ctx.scope.teams:
        raise dag_deploy.DagDeployError(f"the user is not a member of team {team!r}")
    cfg = env_teams[team]
    if not cfg.get("bucket") or not cfg.get("dag_s3_path"):
        # An empty DagS3Path would write to the bucket root, next to requirements and the startup script.
        raise dag_deploy.DagDeployError(
            f"team {team!r} has no DAG folder configured on this environment"
        )
    return team


def check_dag_deploy(
    ctx: SessionContext, file_name: Any, content: Any, team: Any = None
) -> tuple[dag_deploy.DagFile, str | None]:
    """Shared by the approval hook (before asking) and the tool (before writing)."""
    if not dag_deploy.deploy_enabled():
        raise dag_deploy.DagDeployError(
            "DAG deployment is disabled on this agent runtime (ENABLE_DAG_DEPLOY is not true)"
        )
    if not ctx.scope.can_deploy_dags:
        raise dag_deploy.DagDeployError(
            "this user cannot deploy DAGs; it needs edit rights on all DAGs and the Op or Admin role"
        )
    if ctx.dag_deploy_mode != "s3_with_approval":
        raise dag_deploy.DagDeployError(
            f"unsupported dag_deploy_mode {ctx.dag_deploy_mode!r}"
        )
    blocked = deploy_block_reason(ctx)
    if blocked:
        raise dag_deploy.DagDeployError(blocked)
    team_name = check_deploy_team(ctx, team)
    return dag_deploy.validate_dag_file(file_name, content), team_name


def _fitted_json(
    result: dict[str, Any],
    field: str,
    limit: int,
    when_shortened: dict[str, Any] | None = None,
) -> str:
    """Serialize ``result`` within ``limit`` characters by shortening ``result[field]`` from the end.

    clean() would cut the middle out of the JSON instead, which leaves broken JSON and a file with a
    silent gap. JSON escaping can make a character up to twelve characters long, so a file under the byte
    limit can still be too long. Redaction can lengthen the text slightly, hence the margin. Fields in
    ``when_shortened`` are overwritten if the value had to be shortened, such as a checksum.
    """
    text = _to_json(result)
    value = result.get(field)
    if len(text) <= limit - 2_000 or not isinstance(value, str):
        return clean(text, limit)
    while value and len(text) > limit - 2_000:
        value = value[: int(len(value) * 0.8)]
        result = dict(result, **{field: value})
        text = _to_json(result)
    result["truncated"] = f"{field} was shortened to fit one tool result; it ends early"
    result.update(when_shortened or {})
    return clean(_to_json(result), limit)


def _deny(message: str) -> str:
    return _to_json({"error": "DeniedByAgentPolicy", "message": message})


def _parameter_values(params: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    values: list[str] = []
    for key in keys:
        value = params.get(key)
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, list):
            values.extend(str(item) for item in value if isinstance(item, (str, int)))
    return values


MAX_OBSERVED_VALUES = 10_000
_IDENTIFIER_TOKEN = re.compile(r"[A-Za-z0-9_.:/@+-]{3,300}")
_EC2_ID = re.compile(
    r"\b(?:vpc|subnet|sg|rtb|acl|vpce|eni|igw|nat|pl)-[0-9a-f]{8,17}\b"
)
_EC2_ID_FILTERS = frozenset(
    {
        "vpc-id",
        "subnet-id",
        "group-id",
        "vpc-endpoint-id",
        "route-table-id",
        "network-acl-id",
        "association.subnet-id",
        "association.route-table-id",
        "association.network-acl-id",
    }
)
# Filters that can only narrow a result when ANDed with an ID filter.
_EC2_NARROWING_FILTERS = frozenset({"service-name", "vpc-endpoint-type"})


class Provenance:
    """Identifiers seen in authorized responses, split by how much they can be trusted.

    ``strong`` holds whole values of structured fields (rendered fields, XCom, AWS responses) and tokens of
    DAG source, which the DAG author wrote. ``weak`` also holds tokens split out of free text such as task
    log messages, which can echo data from outside (an API response, a file) and so be steered by an
    attacker. Resource names need strong provenance; per-run IDs may come from weak provenance.
    """

    def __init__(self) -> None:
        self.strong: set[str] = set()
        self.weak: set[str] = set()

    def copy(self) -> Provenance:
        other = Provenance()
        other.strong, other.weak = set(self.strong), set(self.weak)
        return other


def _collect_identifiers(
    value: Any,
    sink: Provenance,
    *,
    free_text: bool = False,
    tokens_strong: bool = False,
) -> None:
    """Record values from an authorized response that later calls may use as resource identifiers.

    Short strings are kept whole and also split into tokens: Airflow 3 returns task logs as structured
    events, so an ID such as a Glue run ID usually sits inside a short message ("Exiting Job jr_... Run
    State: FAILED") rather than in a field of its own. With ``free_text`` (task logs), even whole values
    count only as weak provenance. With ``tokens_strong`` (DAG source), tokens count as strong.
    """
    stack = [value]
    # Separate budgets, strong first: a large task log fills the weak set with tokens, and that must not
    # stop later rendered_fields or XCom values from being recorded as strong provenance.
    while stack and (
        len(sink.strong) < MAX_OBSERVED_VALUES or len(sink.weak) < MAX_OBSERVED_VALUES
    ):
        item = stack.pop()
        if isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
        elif isinstance(item, str):
            tokens = _IDENTIFIER_TOKEN.findall(item)[:1000]
            whole = 2 <= len(item) <= 300
            if len(sink.strong) < MAX_OBSERVED_VALUES:
                if whole and not free_text:
                    sink.strong.add(item)
                if tokens_strong:
                    sink.strong.update(tokens)
            if len(sink.weak) < MAX_OBSERVED_VALUES:
                if whole:
                    sink.weak.add(item)
                sink.weak.update(tokens)


# Per-run identifiers are random and only identify one execution, so a value seen in log text is enough.
# Every other identifying parameter names a long-lived resource and needs strong provenance.
_RUN_SCOPED_PARAMS = frozenset(
    {
        "RunId",
        "StepId",
        "jobRunId",
        "QueryExecutionId",
        "Id",
        "executionArn",
        "jobs",
        "tasks",
    }
)


def _validate_linked_resource(
    service: str, operation: str, params: dict[str, Any], observed: Provenance
) -> str | None:
    """Require downstream identifiers to have appeared in an authorized Airflow/AWS response."""
    required: dict[tuple[str, str], tuple[str, ...]] = {
        ("glue", "GetJob"): ("JobName",),
        ("glue", "GetJobRun"): ("JobName", "RunId"),
        ("glue", "GetJobRuns"): ("JobName",),
        ("emr", "DescribeCluster"): ("ClusterId",),
        ("emr", "DescribeStep"): ("ClusterId", "StepId"),
        ("emr", "ListSteps"): ("ClusterId",),
        ("emr-serverless", "GetApplication"): ("applicationId",),
        ("emr-serverless", "GetJobRun"): ("applicationId", "jobRunId"),
        ("athena", "GetQueryExecution"): ("QueryExecutionId",),
        ("redshift-data", "DescribeStatement"): ("Id",),
        ("stepfunctions", "DescribeExecution"): ("executionArn",),
        ("batch", "DescribeJobs"): ("jobs",),
        ("ecs", "DescribeTasks"): ("cluster", "tasks"),
        ("sagemaker", "DescribeTrainingJob"): ("TrainingJobName",),
        ("sagemaker", "DescribeProcessingJob"): ("ProcessingJobName",),
    }
    keys = required.get((service, operation))
    if not keys:
        return None
    if not _parameter_values(params, keys):
        return f"{service}:{operation} needs {', '.join(keys)}"
    for key in keys:
        # Strong provenance also satisfies run-scoped IDs (an XCom run ID), even when the weak set is full.
        trusted = (
            observed.weak | observed.strong
            if key in _RUN_SCOPED_PARAMS
            else observed.strong
        )
        values = _parameter_values(params, (key,))
        if not values or any(value not in trusted for value in values):
            if key in _RUN_SCOPED_PARAMS:
                return (
                    f"{service}:{operation} may only inspect resource identifiers found in this "
                    "session's authorized Airflow context"
                )
            return (
                f"{service}:{operation} {key} must come from the task's rendered fields, XCom, DAG "
                "source, or an AWS response; a name that appears only in log text is not enough. "
                "Read the task instance (rendered_fields) or the DAG source first"
            )
    if service == "stepfunctions":
        # An execution ARN names its state machine, and execution names are often predictable, so the
        # state machine itself needs strong provenance even though the execution part may come from a log.
        arn = str(params.get("executionArn", ""))
        parts = arn.split(":")
        if len(parts) < 8 or parts[5] not in ("execution", "express"):
            return "stepfunctions:DescribeExecution needs a state machine execution ARN"
        machine = parts[6]
        machine_arn = ":".join(parts[:5] + ["stateMachine", machine])
        if machine not in observed.strong and machine_arn not in observed.strong:
            return (
                "stepfunctions:DescribeExecution needs the state machine "
                f"({machine}) from the task's rendered fields, XCom, DAG source, or an AWS response"
            )
    return None


def _readable_task_stream(ctx: SessionContext, stream: Any) -> bool:
    """True if a Task log stream name or prefix stays inside one DAG the user can read.

    MWAA names task log streams dag_id=<dag>/run_id=<run>/task_id=<task>/attempt=<n>.log. The trailing
    slash matters: without it, the prefix "dag_id=etl" would also match the streams of DAG "etl_secret".
    """
    if not isinstance(stream, str) or not stream.startswith("dag_id="):
        return False
    dag_id, sep, _ = stream.removeprefix("dag_id=").partition("/")
    return bool(sep) and ctx.scope.can_read(dag_id)


def _reads_all_dags(ctx: SessionContext) -> bool:
    """all_dags_readable, but never on an environment with teams: there the bucket and log groups mix
    teams. Checked against GetEnvironment, not only the plugin's multi_team flag."""
    if not ctx.scope.all_dags_readable or ctx.scope.multi_team:
        return False
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        return True
    return not (_RESOURCES.environment(ctx).get("teams") or {})


def _team_folders(ctx: SessionContext) -> dict[str, dict[str, str]]:
    """The DAG folders of the user's own teams, from GetEnvironment.Teams (never from the payload)."""
    env_teams = _RESOURCES.environment(ctx).get("teams") or {}
    return {
        name: cfg
        for name, cfg in env_teams.items()
        if name in ctx.scope.teams and cfg.get("bucket") and cfg.get("dag_s3_path")
    }


def _team_folder_read_error(
    ctx: SessionContext, operation: str, params: dict[str, Any]
) -> str | None:
    """None if this S3 read stays inside one of the user's team DAG folders, else a short reason ('' if no
    team folders apply)."""
    folders = _team_folders(ctx)
    if not folders:
        return ""
    bucket = params.get("Bucket")
    if operation in ("ListObjectsV2",):
        path = params.get("Prefix")
    elif operation in ("GetObject", "GetObjectVersion", "HeadObject"):
        path = params.get("Key")
    else:
        return f"{operation} is not available on team folders"
    if not isinstance(path, str) or ".." in path.split("/"):
        return "name a key or prefix inside your team's DAG folder"
    for cfg in folders.values():
        if bucket == cfg["bucket"] and path.startswith(cfg["dag_s3_path"] + "/"):
            return None
    allowed = ", ".join(
        f"s3://{c['bucket']}/{c['dag_s3_path']}/" for c in folders.values()
    )
    return f"readable team folders: {allowed}"


def _airflow_api_disabled(ctx: SessionContext) -> bool:
    """The agent does not call the Airflow REST API on Identity Center environments, unless the runtime is
    configured to (AIRFLOW_API_WITH_IDENTITY_CENTER=true)."""
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        return False
    if os.environ.get("AIRFLOW_API_WITH_IDENTITY_CENTER", "").lower() == "true":
        return False
    try:
        return bool(_RESOURCES.environment(ctx).get("identity_center"))
    except (ClientError, BotoCoreError):
        return False  # the API call itself then reports the real error


def _validate_dag_scoped_reads(
    ctx: SessionContext,
    service: str,
    operation: str,
    params: dict[str, Any],
    group: str,
) -> str | None:
    """Keep S3 and CloudWatch Logs reads inside the user's DAG scope.

    Users who can read every DAG may read the whole bucket and all environment log groups. Other users
    can only reach the bucket and logs through their own DAGs: the bucket holds every DAG's source plus
    the startup script and requirements, and the Scheduler, DAGProcessing, WebServer and Worker log groups
    mix events from all DAGs. For them, only per-DAG streams in the Task log group are readable.
    """
    if _reads_all_dags(ctx):
        return None
    if service == "s3":
        team_error = _team_folder_read_error(ctx, operation, params)
        if team_error is None:
            return None
        hint = (
            "Read DAG source with airflow_api GET /dagSources/<dag_id> instead"
            if not _airflow_api_disabled(ctx)
            else "Only the DAG folders of the user's own teams can be read"
        )
        return (
            "S3 reads need read access to all DAGs, because the bucket holds every DAG's source and the "
            f"environment's startup script and requirements. {hint}"
            + (f" ({team_error})" if team_error else "")
        )
    if service != "logs" or operation == "GetQueryResults":
        return None
    scoped_error = (
        "this user can read only some DAGs, so CloudWatch Logs access is limited to the Task log group "
        f"({group}) and to streams of readable DAGs: name a stream or prefix such as dag_id=<dag_id>/"
    )
    if operation == "StartQuery":
        return (
            "Logs Insights queries can read every DAG's logs, so they need read access to all DAGs. "
            "Use FilterLogEvents or GetLogEvents on a dag_id=<dag_id>/ stream instead"
        )
    if operation == "GetLogEvents":
        streams = [params.get("logStreamName")]
    elif operation == "FilterLogEvents":
        if "logStreamNames" in params and "logStreamNamePrefix" in params:
            return scoped_error
        names = params.get("logStreamNames")
        streams = (
            list(names)
            if isinstance(names, list)
            else [params.get("logStreamNamePrefix")]
        )
    elif operation == "DescribeLogStreams":
        streams = [params.get("logStreamNamePrefix")]
    else:
        return scoped_error
    if not streams or not all(_readable_task_stream(ctx, s) for s in streams):
        return scoped_error
    return None


def _validate_aws_resource(
    ctx: SessionContext,
    service: str,
    operation: str,
    params: dict[str, Any],
    observed: Provenance,
) -> str | None:
    """Constrain model-controlled identifiers to the pinned environment's resources."""
    if os.environ.get("AIRFLOW_API_BASE_URL"):
        return "AWS diagnostic tools are disabled in local-development mode"
    task_group = f"airflow-{ctx.environment_name}-Task"
    env = _RESOURCES.environment(ctx)
    if service == "mwaa" and params.get("Name") != ctx.environment_name:
        return "GetEnvironment may only target the pinned MWAA environment"
    if service == "s3":
        # _team_folder_read_error returns None only for a read inside one of the user's team folders; ""
        # (no team folders) and a reason both mean "not allowed" outside the source bucket.
        if (
            params.get("Bucket") != env["bucket"]
            and _team_folder_read_error(ctx, operation, params) is not None
        ):
            return "S3 reads may only target the pinned environment's source bucket or your team's DAG folder"
        if env["account"]:
            params["ExpectedBucketOwner"] = env["account"]
    if service == "logs":
        allowed = {
            f"airflow-{ctx.environment_name}-DAGProcessing",
            f"airflow-{ctx.environment_name}-Scheduler",
            f"airflow-{ctx.environment_name}-Task",
            f"airflow-{ctx.environment_name}-WebServer",
            f"airflow-{ctx.environment_name}-Worker",
        }
        groups: list[str] = []
        for key in ("logGroupName", "logGroupIdentifier"):
            if key in params:
                groups.append(
                    str(params[key])
                    .removeprefix("arn:aws:logs:")
                    .split(":log-group:")[-1]
                    .removesuffix(":*")
                )
        for key in ("logGroupNames", "logGroupIdentifiers"):
            groups.extend(
                str(v)
                .removeprefix("arn:aws:logs:")
                .split(":log-group:")[-1]
                .removesuffix(":*")
                for v in params.get(key, [])
            )
        if operation != "GetQueryResults" and (
            not groups or any(group not in allowed for group in groups)
        ):
            return "CloudWatch Logs calls must name an exact log group for the pinned environment"
        if not _reads_all_dags(ctx) and any(g != task_group for g in groups):
            return (
                "this user can read only some DAGs, so CloudWatch Logs access is limited to the Task "
                f"log group ({task_group}); the other log groups mix events from all DAGs"
            )
        if operation == "StartQuery":
            if len(str(params.get("queryString", ""))) > 4096:
                return "Logs Insights query exceeds 4096 characters"
            start, end = params.get("startTime"), params.get("endTime")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or end < start
                or end - start > 7 * 24 * 3600
            ):
                return (
                    "Logs Insights time range must be valid and no longer than 7 days"
                )
    if service == "iam":
        if operation in {
            "GetRole",
            "ListAttachedRolePolicies",
            "ListRolePolicies",
            "GetRolePolicy",
        }:
            if params.get("RoleName") != env["execution_role_name"]:
                return "IAM role inspection is limited to the MWAA execution role"
        elif operation == "SimulatePrincipalPolicy":
            if params.get("PolicySourceArn") != env["execution_role_arn"]:
                return "policy simulation is limited to the MWAA execution role"
        elif operation in {"GetPolicy", "GetPolicyVersion"} and params.get(
            "PolicyArn"
        ) not in _RESOURCES.attached_policies(ctx):
            return "managed policy inspection is limited to policies attached to the MWAA execution role"
    if service == "cloudwatch":
        serialized = json.dumps(params, separators=(",", ":"))
        if ctx.environment_name not in serialized:
            return "CloudWatch metrics and alarms must be filtered to the pinned environment name"
    if service in ("s3", "logs"):
        scope_error = _validate_dag_scoped_reads(
            ctx, service, operation, params, task_group
        )
        if scope_error:
            return scope_error
    if service == "ec2":
        # Every EC2 resource ID in the request must come from a structured response (GetEnvironment's
        # NetworkConfiguration, a security group listing), not just one of them. Filter values are ORed
        # and accept wildcards, so a wildcard or a non-ID filter (tag:Name) next to one observed ID would
        # widen the call to the whole account: only ID-typed filters without wildcards are accepted.
        serialized = json.dumps(params, separators=(",", ":"))
        if "*" in serialized or "?" in serialized:
            return "EC2 network inspection does not accept wildcards"
        filters = params.get("Filters") or []
        narrowing = [
            f
            for f in filters
            if isinstance(f, dict) and f.get("Name") in _EC2_NARROWING_FILTERS
        ]
        if not isinstance(filters, list) or any(
            not isinstance(f, dict)
            or f.get("Name") not in _EC2_ID_FILTERS | _EC2_NARROWING_FILTERS
            for f in filters
        ):
            return (
                "EC2 network inspection accepts only ID filters ("
                + ", ".join(sorted(_EC2_ID_FILTERS))
                + "), service-name or vpc-endpoint-type next to one of them, or *Ids parameters"
            )
        if narrowing and len(narrowing) == len(filters):
            # Filters are ANDed, so service-name only narrows an ID filter; on its own it lists every
            # endpoint for that service in the account.
            return "service-name and vpc-endpoint-type filters need a vpc-id or other ID filter"
        id_values = json.dumps(
            {k: v for k, v in params.items() if k != "Filters"}
            | {"Filters": [f for f in filters if f not in narrowing]},
            separators=(",", ":"),
        )
        ids = set(_EC2_ID.findall(id_values))
        if not ids or not ids <= observed.strong:
            return (
                "EC2 network inspection must use only IDs found in the pinned environment's "
                "network configuration or other AWS responses"
            )
    linked_error = _validate_linked_resource(service, operation, params, observed)
    if linked_error:
        return linked_error
    return None


def build_tools(
    get_context: ContextGetter,
    skills_dir: Path,
    deploy_approvals: dag_deploy.ApprovedDeploys | None = None,
) -> list:
    """Build the tools. Pass the same ``deploy_approvals`` to ApprovalHook, so uploads bind to approvals."""
    deploy_approvals = deploy_approvals or dag_deploy.DEFAULT_APPROVALS
    allowed_query_ids: set[str] = set()
    observed_resource_values = Provenance()
    observed_lock = threading.Lock()

    def remember(
        value: Any, *, free_text: bool = False, tokens_strong: bool = False
    ) -> None:
        with observed_lock:
            _collect_identifiers(
                value,
                observed_resource_values,
                free_text=free_text,
                tokens_strong=tokens_strong,
            )

    @tool
    def aws_api(
        service: str,
        operation: str,
        params: dict | None = None,
        region: str | None = None,
    ) -> str:
        """Call one reviewed, read-only AWS API for this environment.

        Use canonical API operation names (for example GetEnvironment). Calls are pinned to the environment's
        Region. S3, Logs, MWAA, and IAM calls are resource-scoped by code. Local-development mode disables this
        tool because its credentials are only for model invocation. Paginate in separate calls.
        """
        ctx = get_context()
        op = normalize_operation(operation)
        decision = policy.check_aws(service, op)
        if not decision.allowed:
            return _deny(decision.reason)
        if region and region != ctx.region:
            return _deny("cross-Region AWS calls are disabled")
        if not _REGION.fullmatch(ctx.region):
            return _to_json(
                {
                    "error": "InvalidRegion",
                    "message": "the pinned environment Region is invalid",
                }
            )
        call_params = dict(params or {})
        try:
            if (
                len(json.dumps(call_params, separators=(",", ":")).encode())
                > MAX_AWS_PARAMS_BYTES
            ):
                return _deny(f"AWS parameters exceed {MAX_AWS_PARAMS_BYTES} bytes")
        except (TypeError, ValueError):
            return _deny("AWS parameters must be JSON serializable")
        if (
            service == "logs"
            and op == "GetQueryResults"
            and call_params.get("queryId") not in allowed_query_ids
        ):
            return _deny(
                "GetQueryResults may only read a query started by this agent session"
            )
        try:
            with observed_lock:
                observed_snapshot = observed_resource_values.copy()
            resource_error = _validate_aws_resource(
                ctx, service, op, call_params, observed_snapshot
            )
            if resource_error:
                return _deny(resource_error)
            client = boto3.client(service, region_name=ctx.region, config=_BOTO_CONFIG)
            # Exact operation lookup through the service model prevents mixed-case aliases.
            if op not in client.meta.service_model.operation_names:
                return _deny(f"{service}:{op} is not a canonical API operation")
            method = getattr(
                client,
                client.meta.method_to_api_mapping
                and next(
                    name
                    for name, api_name in client.meta.method_to_api_mapping.items()
                    if api_name == op
                ),
            )
            response = method(**call_params)
        except (
            ClientError,
            BotoCoreError,
            TypeError,
            ValueError,
            StopIteration,
        ) as err:
            return _client_error(err)
        response.pop("ResponseMetadata", None)
        # Logs responses are task and scheduler log text; everything else is structured AWS data.
        remember(response, free_text=service == "logs")
        if service == "logs" and op == "StartQuery" and response.get("queryId"):
            allowed_query_ids.add(str(response["queryId"]))
        if (
            service == "s3"
            and op in {"GetObject", "GetObjectVersion"}
            and "Body" in response
        ):
            body = response.pop("Body")
            data = body.read(MAX_S3_OBJECT_BYTES + 1)
            body.close()
            response["Body"] = data[:MAX_S3_OBJECT_BYTES].decode(
                "utf-8", errors="replace"
            )
            if len(data) > MAX_S3_OBJECT_BYTES:
                response["BodyTruncated"] = (
                    f"only the first {MAX_S3_OBJECT_BYTES} bytes are shown"
                )
        return clean(_to_json(response))

    @tool
    def airflow_api(
        method: str, path: str, query: dict | None = None, body: dict | None = None
    ) -> str:
        """Call the pinned environment's Airflow REST API.

        GET calls are DAG-scoped. Allowed mutations are schema-checked, DAG-scoped, and always shown to the
        user for explicit approval. Connections, variables, configuration, identities, and arbitrary routes
        are unavailable.
        """
        ctx = get_context()
        method_u = method.upper()
        if method_u not in ("GET", "POST", "PATCH"):
            return _deny("only GET, POST and PATCH are allowed")
        decision = policy.check_airflow(ctx.scope, method_u, path, body, query)
        if not decision.allowed:
            return _deny(decision.reason)
        if _airflow_api_disabled(ctx):
            return _to_json(
                {
                    "error": "AirflowApiUnavailable",
                    "message": (
                        "The agent does not call the Airflow REST API on environments that use IAM "
                        "Identity Center, so it cannot read or change Airflow state here. Tell the user, "
                        "and use aws_api instead: CloudWatch Task log streams of their DAGs, and S3 reads "
                        "of their team's DAG folder."
                    ),
                }
            )
        try:
            result = make_backend(ctx.environment_name, ctx.region).call(
                method_u, path, query, body
            )
            remember(
                result,
                free_text="/logs" in path,
                tokens_strong=path.startswith("/dagSources/"),
            )
        except AirflowBackendError as err:
            return clean(_to_json(err.payload))
        except (ClientError, BotoCoreError, TypeError, ValueError, OSError) as err:
            return _client_error(err)
        return clean(_to_json(result))

    @tool
    def read_skill_file(skill_name: str, path: str) -> str:
        """Read a bundled skill reference file. No other filesystem access is available."""
        base = skills_dir.resolve()
        skill_root = (base / skill_name).resolve()
        target = (skill_root / path).resolve()
        if skill_root.parent != base or not target.is_relative_to(skill_root):
            return _to_json(
                {
                    "error": "InvalidPath",
                    "message": "path must stay inside the skill directory",
                }
            )
        if not target.is_file():
            return _to_json(
                {"error": "NotFound", "message": f"{skill_name}/{path} does not exist"}
            )
        with target.open("rb") as source:
            data = source.read(MAX_SKILL_FILE_BYTES + 1)
        text = data[:MAX_SKILL_FILE_BYTES].decode("utf-8", errors="replace")
        if len(data) > MAX_SKILL_FILE_BYTES:
            text += f"\n\n[truncated after {MAX_SKILL_FILE_BYTES} bytes]"
        return text

    @tool
    def deploy_dag(
        file_name: str, content: str, overwrite: bool = False, team: str | None = None
    ) -> str:
        """Deploy one DAG file to the top level of the environment's DAG folder, after user approval.

        Pass the complete Python source. On a multi-team environment, pass team= one of the user's teams:
        the file goes to that team's DAG folder (bundle team_<team>); the global folder is not available.
        The user sees the full file, its SHA-256, and the target before anything is written. Set overwrite=true only to replace a file you have read and the user asked to
        change. Afterwards, check /importErrors and /dags/<dag_id> with airflow_api: the scheduler picks up
        new files after its next DAG folder scan, which can take a few minutes on MWAA.
        """
        ctx = get_context()
        try:
            dag, team_name = check_dag_deploy(ctx, file_name, content, team)
            target = deploy_target(ctx, team_name)
            approved, expected = deploy_approvals.take(
                dag, target.describe(dag.file_name)
            )
            if not approved:
                return _deny(
                    "deploy_dag writes only a file the user approved on its approval card"
                )
            if expected is not None and overwrite is not True:
                return _deny(
                    f"{dag.file_name} already exists; set overwrite=true to replace it"
                )
            result = target.write(dag, expected)
        except dag_deploy.DagDeployError as err:
            return _deny(str(err))
        except (ClientError, BotoCoreError, OSError) as err:
            return _client_error(err)
        if not dag.has_dag:
            result["warning"] = (
                "no DAG(...) or @dag found; the file may not define a DAG"
            )
        return clean(_to_json(result))

    @tool
    def list_dag_files(team: str | None = None) -> str:
        """List the Python files in the DAG folder the user may read, with their sizes.

        On a multi-team environment pass team= one of the user's teams. Use it to find a file that fails to
        import, or to scan a folder before an Airflow upgrade.
        """
        ctx = get_context()
        try:
            folder = readable_dag_folder(ctx, team)
            files, truncated = folder.list_files()
        except dag_files.DagFileError as err:
            return _deny(str(err))
        except (ClientError, BotoCoreError, OSError) as err:
            return _client_error(err)
        result: dict[str, Any] = {"folder": folder.describe, "files": files}
        if truncated:
            result["truncated"] = (
                f"only the first {dag_files.MAX_LIST_ENTRIES} files are listed"
            )
        return clean(_to_json(result))

    @tool
    def read_dag_file(path: str, team: str | None = None) -> str:
        """Read one Python file from the DAG folder the user may read (path relative to that folder).

        Use it when /dagSources has no source (the file fails to import) or before you change a file.
        Credential-shaped values come back redacted; never deploy a file that still contains [REDACTED].
        """
        ctx = get_context()
        try:
            folder = readable_dag_folder(ctx, team)
            source = folder.read(path)
        except dag_files.DagFileError as err:
            return _deny(str(err))
        except (ClientError, BotoCoreError, OSError) as err:
            return _client_error(err)
        # DAG source is written by the DAG author, like /dagSources: its names count as strong provenance.
        remember(source.content, tokens_strong=True)
        content = redact(source.content)
        result: dict[str, Any] = {
            "folder": folder.describe,
            "path": source.path,
            "bytes": source.size,
            "sha256": source.sha256,
            "content": content,
        }
        if content != source.content:
            result["redacted"] = (
                "credential-shaped values were replaced with [REDACTED]; edit around them, and tell the "
                "user to move the secret to an Airflow connection or AWS Secrets Manager"
            )
        if source.truncated:
            result["truncated"] = (
                f"only the first {dag_files.MAX_READ_BYTES} bytes are shown"
            )
        # deploy_dag writes only top-level files up to its size limit; say so instead of letting the model
        # try to redeploy a nested or large file under another name.
        result["redeployable_with_deploy_dag"] = (
            "/" not in source.path
            and not source.truncated
            and content == source.content
            and source.size <= dag_deploy.MAX_DAG_FILE_BYTES
        )
        return _fitted_json(
            result,
            "content",
            MAX_DAG_READ_CHARS,
            when_shortened={"sha256": None, "redeployable_with_deploy_dag": False},
        )

    @tool
    def lint_dag(
        content: str | None = None,
        path: str | None = None,
        team: str | None = None,
        fix: bool = False,
    ) -> str:
        """Check a DAG file with Ruff's Airflow rules: code that breaks or is deprecated on Airflow 3, Airflow
        best practices, syntax errors and undefined names. Ruff only parses the file; nothing runs.

        Pass either content (a file you wrote) or path (a file in the readable DAG folder, see
        list_dag_files). With fix=true the result also has fixed_content with Ruff's safe fixes applied.
        Lint a DAG before deploy_dag, and every file when the user asks about an Airflow upgrade.
        """
        ctx = get_context()
        if (content is None) == (path is None):
            return _deny("pass either content or path")
        try:
            if path is not None:
                source = readable_dag_folder(ctx, team).read(path)
                if source.truncated:
                    return _deny(
                        f"{path} is larger than {dag_files.MAX_READ_BYTES} bytes and cannot be linted"
                    )
                remember(source.content, tokens_strong=True)
                content, name = source.content, path
            else:
                name = "dag.py"
            result = dag_lint.lint_source(content, name, fix=fix is True)
        except (dag_files.DagFileError, dag_lint.DagLintError) as err:
            return _deny(str(err))
        except (ClientError, BotoCoreError, OSError) as err:
            return _client_error(err)
        summary = dag_lint.result_summary(result)
        summary["airflow_version"] = ctx.airflow_version
        if path is not None:
            summary["path"] = path
        fixed = summary.get("fixed_content")
        if isinstance(fixed, str) and redact(fixed) != fixed:
            summary["fixed_content_redacted"] = (
                "credential-shaped values were replaced with [REDACTED], so this content cannot be deployed "
                "as is; the secret must move to an Airflow connection or AWS Secrets Manager"
            )
        return _fitted_json(summary, "fixed_content", MAX_DAG_READ_CHARS)

    return [
        aws_api,
        airflow_api,
        read_skill_file,
        deploy_dag,
        list_dag_files,
        read_dag_file,
        lint_dag,
    ]
