# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import pytest
from mwaa_agent import policy
from mwaa_agent.policy import TIER_OPERATE, TIER_READ, AccessScope


@pytest.mark.parametrize(
    "service,operation",
    [
        ("mwaa", "GetEnvironment"),
        ("logs", "FilterLogEvents"),
        ("logs", "StartQuery"),
        ("s3", "GetObject"),
        ("s3", "ListObjectsV2"),
        ("glue", "GetJobRun"),
        ("iam", "SimulatePrincipalPolicy"),
    ],
)
def test_reads_are_allowed(service, operation):
    assert policy.check_aws(service, operation).allowed


@pytest.mark.parametrize(
    "service,operation",
    [
        ("secretsmanager", "GetSecretValue"),  # service not allowed at all
        ("mwaa", "CreateCliToken"),
        ("mwaa", "CreateWebLoginToken"),
        ("mwaa", "InvokeRestApi"),  # must go through airflow_api
        ("mwaa", "UpdateEnvironment"),
        ("mwaa", "DeleteEnvironment"),
        ("s3", "PutObject"),
        ("s3", "DeleteObject"),
        ("sts", "GetSessionToken"),
        ("sts", "AssumeRole"),
        ("kms", "Decrypt"),
        ("ssm", "GetParameter"),
        ("lambda", "GetFunction"),
        ("iam", "GetCredentialReport"),
        ("ec2", "GetPasswordData"),
        ("glue", "StartJobRun"),
        ("iam", "PutRolePolicy"),
        ("cloudtrail", "LookupEvents"),
        ("stepfunctions", "GetActivityTask"),
        ("lambda", "GetFunctionConfiguration"),
        ("ecs", "DescribeTaskDefinition"),
        ("glue", "GetCONNECTION"),
        ("ec2", "GetPASSWORDData"),
    ],
)
def test_writes_and_secrets_are_denied(service, operation):
    assert not policy.check_aws(service, operation).allowed


def test_operation_allowlist_is_exact_and_canonical():
    assert policy.check_aws("glue", "GetJobRun").allowed
    assert not policy.check_aws("glue", "GetJOBRun").allowed
    assert not policy.check_aws("glue", "GetConnection").allowed


READER = AccessScope(tier=TIER_READ, readable_dags=frozenset({"etl"}))
OPERATOR = AccessScope(
    tier=TIER_OPERATE,
    readable_dags=frozenset({"etl", "report"}),
    runnable_dags=frozenset({"etl"}),
    can_edit_task_instances=True,
    can_edit_runs=True,
)
ADMIN = AccessScope(
    tier=TIER_OPERATE,
    all_dags_readable=True,
    runnable_dags=frozenset({"etl", "report"}),
    can_edit_task_instances=True,
    can_edit_runs=True,
)
# A custom role that may edit DAGs and create runs, but not edit task instances or runs.
TRIGGER_ONLY = AccessScope(
    tier=TIER_OPERATE,
    readable_dags=frozenset({"etl"}),
    runnable_dags=frozenset({"etl"}),
)


@pytest.mark.parametrize(
    "method,path,body",
    [
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {"dag_run_id": "r1", "task_ids": ["t"], "dry_run": False},
        ),
        ("PATCH", "/dags/etl/dagRuns/r1", {"state": "failed"}),
        ("PATCH", "/dags/etl/dagRuns/r1/taskInstances/t", {"new_state": "success"}),
    ],
)
def test_mutations_need_their_own_airflow_permission(method, path, body):
    decision = policy.check_airflow(TRIGGER_ONLY, method, path, body)
    assert not decision.allowed and "Airflow role cannot" in decision.reason
    assert policy.check_airflow(OPERATOR, method, path, body).needs_approval


def test_trigger_and_pause_need_only_the_operate_tier():
    assert policy.check_airflow(
        TRIGGER_ONLY, "POST", "/dags/etl/dagRuns", {}
    ).needs_approval
    assert policy.check_airflow(
        TRIGGER_ONLY, "PATCH", "/dags/etl", {"is_paused": True}
    ).needs_approval


@pytest.mark.parametrize(
    "path",
    [
        "/connections",
        "/connections/aws_default",
        "/variables/x",
        "/config",
        "/users",
        "/roles",
        "/auth/token",
    ],
)
def test_secret_endpoints_denied_even_for_admin(path):
    assert not policy.check_airflow(ADMIN, "GET", path).allowed


def test_dag_scoped_reads():
    assert policy.check_airflow(READER, "GET", "/dags/etl/dagRuns").allowed
    assert policy.check_airflow(READER, "GET", "/dagSources/etl").allowed
    assert not policy.check_airflow(READER, "GET", "/dags/report/dagRuns").allowed
    assert not policy.check_airflow(READER, "GET", "/dags/~/dagRuns").allowed
    assert not policy.check_airflow(READER, "GET", "/dags").allowed
    assert not policy.check_airflow(READER, "GET", "/importErrors").allowed
    assert policy.check_airflow(READER, "GET", "/version").allowed
    assert not policy.check_airflow(ADMIN, "GET", "/dags/~/dagRuns").allowed
    assert policy.check_airflow(ADMIN, "GET", "/importErrors").allowed


@pytest.mark.parametrize(
    "path", ["/dags/etl/../report", "/dags/etl?x=1", "dags/etl", "/dags/etl#x"]
)
def test_malformed_paths_denied(path):
    assert not policy.check_airflow(ADMIN, "GET", path).allowed


def test_read_tier_cannot_mutate():
    decision = policy.check_airflow(READER, "POST", "/dags/etl/dagRuns", {})
    assert not decision.allowed


def test_operate_tier_mutations_need_approval_and_scope():
    trigger = policy.check_airflow(
        OPERATOR, "POST", "/dags/etl/dagRuns", {"dag_run_id": "t1"}
    )
    assert trigger.allowed and trigger.needs_approval
    assert policy.check_airflow(
        OPERATOR,
        "POST",
        "/dags/etl/clearTaskInstances",
        {"dag_run_id": "r1", "task_ids": ["t"], "dry_run": False},
    ).needs_approval
    assert policy.check_airflow(
        OPERATOR, "PATCH", "/dags/etl", {"is_paused": False}
    ).needs_approval
    assert policy.check_airflow(
        OPERATOR, "PATCH", "/dags/etl/dagRuns/r1", {"state": "failed"}
    ).needs_approval
    assert policy.check_airflow(
        OPERATOR,
        "PATCH",
        "/dags/etl/dagRuns/r1/taskInstances/t/2",
        {"new_state": "failed"},
    ).needs_approval
    # readable but not runnable
    assert not policy.check_airflow(
        OPERATOR, "POST", "/dags/report/dagRuns", {}
    ).allowed
    # wildcard and unknown mutations
    assert not policy.check_airflow(ADMIN, "POST", "/dags/~/dagRuns", {}).allowed
    assert not policy.check_airflow(OPERATOR, "DELETE", "/dags/etl", None).allowed
    assert not policy.check_airflow(
        OPERATOR, "PATCH", "/dags/etl", {"is_paused": True, "owners": ["x"]}
    ).allowed
    assert not policy.check_airflow(OPERATOR, "POST", "/dagSources/etl", {}).allowed
    assert not policy.check_airflow(OPERATOR, "POST", "/pools", {}).allowed


def test_describe_mutation():
    assert (
        policy.describe_mutation("POST", "/dags/etl/dagRuns")
        == "trigger a DAG run for DAG 'etl'"
    )


@pytest.mark.parametrize(
    "method,path,body,query",
    [
        ("PATCH", "/dags/etl", {"is_paused": "false"}, None),
        ("PATCH", "/dags/etl/dagRuns/r1", {"unexpected": "x"}, None),
        ("POST", "/dags/etl/dagRuns", {"conf": {"x": "y" * 70_000}}, None),
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {"dag_run_id": "r", "task_ids": [], "dry_run": False},
            None,
        ),
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {"dag_run_id": None, "task_ids": ["t"], "dry_run": False},
            None,
        ),
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {"dag_run_id": ["r"], "task_ids": ["t"], "dry_run": False},
            None,
        ),
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {
                "dag_run_id": "r",
                "task_ids": ["t"],
                "dry_run": False,
                "start_date": "2020-01-01",
            },
            None,
        ),
        # Airflow would silently default dry_run to true, so it must be explicit.
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {"dag_run_id": "r", "task_ids": ["t"]},
            None,
        ),
        # Airflow 3 forbids these (422).
        (
            "POST",
            "/dags/etl/clearTaskInstances",
            {
                "dag_run_id": "r",
                "task_ids": ["t"],
                "dry_run": False,
                "include_subdags": True,
            },
            None,
        ),
        ("GET", "/dags/etl/dagRuns", None, {"limit": 1001}),
        ("GET", "/dags/etl/dagRuns", None, {"x": "y" * 9000}),
    ],
)
def test_airflow_body_and_query_schema_rejects_bad_input(method, path, body, query):
    assert not policy.check_airflow(OPERATOR, method, path, body, query).allowed


@pytest.mark.parametrize(
    "path",
    ["/%63onnections", "/dags/etl/%2e%2e/connections", "/dags/etl\\x", "/dags//etl"],
)
def test_encoded_or_noncanonical_paths_denied(path):
    assert not policy.check_airflow(ADMIN, "GET", path).allowed


def test_truncated_dag_lists_explain_the_denial():
    scope = AccessScope(
        tier=TIER_READ, readable_dags=frozenset({"etl"}), dag_lists_truncated=True
    )
    decision = policy.check_airflow(scope, "GET", "/dags/other")
    assert not decision.allowed and "open this DAG's page" in decision.reason
    assert (
        "open this DAG's page"
        not in policy.check_airflow(READER, "GET", "/dags/other").reason
    )


@pytest.mark.parametrize("path", ["/plugins", "/providers"])
def test_routes_the_mwaa_user_role_cannot_read_are_not_offered(path):
    # On MWAA the agent calls Airflow as the User role, which has no Plugins or Providers permission.
    assert not policy.check_airflow(ADMIN, "GET", path).allowed
