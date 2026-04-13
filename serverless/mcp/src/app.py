"""MCP Server Lambda handler for MWAA Serverless DAG Factory YAML assistant."""

import json
import logging
import os
from typing import Optional

from awslabs.mcp_lambda_handler import MCPLambdaHandler
from tools import generate_yaml, validate_yaml, list_operators, list_unsupported, get_constraints, get_overview, generate_execution_role_policy, get_service_tasks as _get_service_tasks, compose_dag_yaml as _compose_dag_yaml
from python_analyzer import analyze_python_dag
from python_converter import convert_python_to_yaml
from operations import (
    list_workflows as _list_workflows,
    get_workflow as _get_workflow,
    start_workflow_run as _start_workflow_run,
    get_workflow_run_status as _get_workflow_run_status,
    stop_workflow_run as _stop_workflow_run,
    find_workflows_using_service as _find_workflows_using_service,
    deploy_and_run as _deploy_and_run,
    poll_workflow_run as _poll_workflow_run,
    get_failed_runs_summary as _get_failed_runs_summary,
    delete_workflows as _delete_workflows,
    list_runs as _list_runs,
    get_workflow_summary as _get_workflow_summary,
    bulk_status as _bulk_status,
    redeploy_workflow as _redeploy_workflow,
    compare_versions as _compare_versions,
)

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

mcp_server = MCPLambdaHandler(name="mwaa-serverless-dag-factory", version="2.0.0")


@mcp_server.tool()
def generate_dag_yaml(dag_id: str, service: str, description: str = "", schedule: str = "None", params: Optional[dict] = None) -> str:
    """Generate an MWAA Serverless DAG factory YAML. Uses array-based tasks with short operator names (e.g. 'GlueJobOperator'), operator params inside 'parameters' object, and upstream_tasks/downstream_tasks for dependencies. Only supported Jinja variables (ds, ds_nodash, ts, ts_nodash, params, ti, macros). IMPORTANT GUIDELINES: (1) Generated templates are SELF-CONTAINED: they use CloudFormationCreateStackOperator with inline TemplateBody to provision any prerequisite resources (SQS queues, SNS topics, Lambda functions, Step Functions state machines, etc.) so the DAG can run without any pre-existing infrastructure. (2) Always include cleanup tasks (CloudFormationDeleteStackOperator with trigger_rule: all_done) to tear down provisioned resources. (3) Always use params with working default values. (4) Call get_serverless_overview first to understand the deployment model. AFTER generating YAML: (a) Always call validate_dag_yaml to check for errors. (b) Always call generate_execution_role to produce a permissive IAM role and policy covering all operators in the DAG, and provide the CLI commands to the user.

    Args:
        dag_id: Unique DAG identifier
        service: s3, glue, athena, bedrock, lambda, emr_serverless, emr, batch, step_functions, redshift, sns, sqs, ecs, eks, cloudformation, sagemaker, rds, ec2, eventbridge, comprehend, dms, kinesis_analytics, neptune, glacier, datasync, appflow, quicksight, dynamodb, opensearch_serverless
        description: DAG description
        schedule: Cron expression, preset (@daily), or None
        params: DAG-level params to override defaults
    """
    return generate_yaml(dag_id, service, description, schedule, params)


@mcp_server.tool()
def validate_dag_yaml(yaml_content: str) -> str:
    """Validate YAML against the MWAA Serverless DAG YAML schema: tasks as array with task_id+operator required, operator from allowlist (short name or FQN), parameters in 'parameters' object, upstream_tasks/downstream_tasks for deps, retries 0-3, retry_delay/execution_timeout as duration strings (e.g. '5m'), no deferrable/dynamic mapping, supported Jinja only.

    Args:
        yaml_content: YAML content to validate
    """
    return json.dumps(validate_yaml(yaml_content), indent=2)


@mcp_server.tool()
def list_supported_operators(service_filter: str = "") -> str:
    """List supported operators (short name + FQN). Includes EmptyOperator and all AWS provider operators/sensors.

    Args:
        service_filter: Filter by name
    """
    return json.dumps(list_operators(service_filter), indent=2)


@mcp_server.tool()
def get_serverless_constraints() -> str:
    """Get all MWAA Serverless constraints: Jinja vars/macros, DAG/task params, AWS base attrs, API actions."""
    return json.dumps(get_constraints(), indent=2)


@mcp_server.tool()
def get_serverless_overview() -> str:
    """Get an overview of how Amazon MWAA Serverless works, including: what it is, how it differs from classic MWAA, the deployment workflow (S3 bucket, execution role, create-workflow, start-workflow-run), workflow types, prerequisites, available regions, CLI commands, and DAG authoring guidelines. IMPORTANT: MWAA Serverless uses the 'mwaa-serverless' service (NOT 'mwaa'). There are no environments — the unit of deployment is a 'workflow'. DAG AUTHORING RULES: (1) Use CloudFormationCreateStackOperator with inline TemplateBody to provision ALL prerequisite resources needed for testing (SQS queues, SNS topics, Lambda functions, Step Functions state machines, IAM roles for those services, etc.) so DAGs are fully self-contained and can run without any pre-existing infrastructure. (2) Always clean up created resources with CloudFormationDeleteStackOperator (trigger_rule: all_done) unless told otherwise. (3) Always use params with working defaults. WORKFLOW RULES: When asked to CREATE a DAG: generate YAML, validate it, then call generate_execution_role to produce a permissive IAM role/policy scoped to the DAG's operators, and provide all CLI commands. When asked to TEST a DAG: generate YAML, validate it, create the IAM role, upload YAML to S3, create/update the workflow, start a run, poll for completion, and surface any failures with error details. Always call this tool first before attempting to deploy or manage MWAA Serverless workflows."""
    return json.dumps(get_overview(), indent=2)


@mcp_server.tool()
def analyze_python_dag_tool(python_source: str) -> str:
    """Analyze Python DAG source code for MWAA Serverless compatibility issues. Checks for: unsupported operators (PythonOperator, BashOperator), @task/@dag decorators, python_callable, deferrable=True, .expand() dynamic mapping, callbacks, operators not in the allowlist, and DAG params that are ignored. Returns errors (blockers), warnings (ignored params), and info.

    Args:
        python_source: Python DAG source code to analyze
    """
    return json.dumps(analyze_python_dag(python_source), indent=2)


@mcp_server.tool()
def convert_python_to_yaml_tool(python_source: str) -> str:
    """Convert a Python DAG file to MWAA Serverless YAML. Extracts DAG structure via AST: task IDs, operators, parameters, >> dependency chains. Supported operators map to short names. Unsupported operators like PythonOperator/BashOperator are replaced with EmptyOperator (flagged for review). Returns the YAML, any errors, and a list of replacements made.

    Args:
        python_source: Python DAG source code to convert
    """
    return json.dumps(convert_python_to_yaml(python_source), indent=2)


@mcp_server.tool()
def generate_execution_role(yaml_content: str) -> str:
    """Generate an IAM execution role policy and CLI commands for deploying an MWAA Serverless workflow. Analyzes the DAG YAML to detect which AWS services are used by operators, then produces: (1) a trust policy for airflow-serverless.amazonaws.com, (2) a permissions policy covering all detected services plus CloudWatch Logs, (3) ready-to-run AWS CLI commands to create the role and attach the policy. IMPORTANT: Always call this after generating a DAG YAML, and provide the commands to the user as part of the deployment instructions.

    Args:
        yaml_content: The DAG YAML content to analyze for required permissions
    """
    return json.dumps(generate_execution_role_policy(yaml_content), indent=2)


@mcp_server.tool()
def get_service_tasks_tool(service: str) -> str:
    """Get the task definitions for a single service as a reusable building block. Returns the tasks dict, default params, and service name. Use this to inspect or compose multi-service DAGs with compose_dag_yaml.

    Args:
        service: Service name (e.g. s3, glue, athena, bedrock, lambda, etc.)
    """
    return json.dumps(_get_service_tasks(service), indent=2, default=str)


@mcp_server.tool()
def compose_dag_yaml_tool(dag_id: str, services_config: list, description: str = "", schedule: str = "None", params: Optional[dict] = None) -> str:
    """Compose a multi-service DAG from multiple service task blocks. Each service's tasks are prefixed to avoid ID collisions, params are namespaced, and cross-service dependencies are wired automatically. After composing, always validate with validate_dag_yaml and generate an execution role with generate_execution_role.

    Args:
        dag_id: Unique DAG identifier
        services_config: List of service configs, each with: service (name), task_prefix (optional, defaults to service name), depends_on (list of upstream task_prefix values). Example: [{"service": "s3", "task_prefix": "s3"}, {"service": "glue", "task_prefix": "glue", "depends_on": ["s3"]}]
        description: DAG description
        schedule: Cron expression, preset (@daily), or None
        params: DAG-level params to override defaults (keys should be prefixed, e.g. s3_bucket_name)
    """
    return _compose_dag_yaml(dag_id, services_config, description, schedule, params)


@mcp_server.tool()
def mwaa_list_workflows(name_contains: str = "", status: str = "") -> str:
    """List MWAA Serverless workflows. Returns compact summary: name, status, trigger_mode, ARN, last modified. Filters by name substring and/or status (READY, CREATING, etc.).

    Args:
        name_contains: Optional substring to filter workflow names (case-insensitive)
        status: Optional status filter (READY, CREATING, UPDATING, DELETING, FAILED)
    """
    return json.dumps(_list_workflows(name_contains, status), indent=2, default=str)


@mcp_server.tool()
def mwaa_get_workflow(workflow_name: str) -> str:
    """Get detailed info about an MWAA Serverless workflow including its DAG YAML definition, operators used, execution role, and S3 location. Supports exact or partial name matching.

    Args:
        workflow_name: Workflow name (exact or partial match)
    """
    return json.dumps(_get_workflow(workflow_name), indent=2, default=str)


@mcp_server.tool()
def mwaa_start_run(workflow_name: str) -> str:
    """Start a workflow run by name. Returns the run ID for tracking.

    Args:
        workflow_name: Workflow name (exact or partial match)
    """
    return json.dumps(_start_workflow_run(workflow_name), indent=2, default=str)


@mcp_server.tool()
def mwaa_get_run_status(workflow_name: str, run_id: str = "") -> str:
    """Get the status of a workflow run including per-task status and error details. If no run_id is provided, returns the latest run.

    Args:
        workflow_name: Workflow name (exact or partial match)
        run_id: Optional specific run ID. If omitted, returns the latest run.
    """
    return json.dumps(_get_workflow_run_status(workflow_name, run_id), indent=2, default=str)


@mcp_server.tool()
def mwaa_stop_run(workflow_name: str, run_id: str = "") -> str:
    """Stop a running workflow. If no run_id, stops the latest active run.

    Args:
        workflow_name: Workflow name (exact or partial match)
        run_id: Optional specific run ID. If omitted, stops the latest active run.
    """
    return json.dumps(_stop_workflow_run(workflow_name, run_id), indent=2, default=str)


@mcp_server.tool()
def mwaa_find_workflows_by_service(service: str) -> str:
    """Find all workflows that use operators for a specific AWS service by inspecting their actual DAG YAML definitions (not just names). Returns matching workflows with the specific tasks/operators found.

    Args:
        service: AWS service name (e.g. step_functions, s3, glue, lambda, bedrock, sqs, sns, ecs, etc.)
    """
    return json.dumps(_find_workflows_using_service(service), indent=2, default=str)


@mcp_server.tool()
def mwaa_deploy_and_run(workflow_name: str, yaml_content: str, s3_bucket: str, execution_role_arn: str, s3_key: str = "") -> str:
    """Deploy and run a workflow in a single call. Uploads YAML to S3, creates the workflow (or updates if it exists), and starts a run. Returns workflow ARN, run ID, and status. Replaces the multi-step deploy flow (S3 upload + create-workflow + start-run) with one call.

    Args:
        workflow_name: Name for the workflow
        yaml_content: The DAG YAML content to deploy
        s3_bucket: S3 bucket for storing the YAML definition
        execution_role_arn: IAM execution role ARN for the workflow
        s3_key: Optional S3 key. Defaults to workflows/{workflow_name}.yaml
    """
    return json.dumps(_deploy_and_run(workflow_name, yaml_content, s3_bucket, execution_role_arn, s3_key), indent=2, default=str)


@mcp_server.tool()
def mwaa_poll_run(workflow_name: str, run_id: str = "", max_seconds: int = 25) -> str:
    """Poll a workflow run until it reaches a terminal state (SUCCESS/FAILED/STOPPED/TIMEOUT) or the polling timeout is reached. If still running after max_seconds, returns current status with completed=false — call again to continue polling. Eliminates repeated check-status calls.

    Args:
        workflow_name: Workflow name (exact or partial match)
        run_id: Optional run ID. If omitted, polls the latest run.
        max_seconds: Max seconds to poll (default 25, capped by Lambda timeout)
    """
    return json.dumps(_poll_workflow_run(workflow_name, run_id, max_seconds), indent=2, default=str)


@mcp_server.tool()
def mwaa_get_failed_runs(name_contains: str = "", hours_back: int = 24, analyze: bool = True) -> str:
    """Scan all workflows for recent failed runs, collect error messages, and optionally analyze failures with Bedrock AI. Returns a consolidated report with: per-workflow failure details, error messages, and AI-generated root cause analysis with suggested fixes. Replaces manual iteration over workflows + runs + error interpretation.

    Args:
        name_contains: Optional filter to scan only workflows matching this substring
        hours_back: How far back to look for failures (default 24 hours)
        analyze: Whether to include Bedrock AI analysis of failures (default true)
    """
    return json.dumps(_get_failed_runs_summary(name_contains, hours_back, analyze), indent=2, default=str)


@mcp_server.tool()
def mwaa_delete_workflows(name_contains: str = "", not_run_in_days: int = 0, dry_run: bool = True) -> str:
    """Delete workflows matching criteria. Supports bulk deletion by name pattern (e.g. 'test') or by inactivity (e.g. not run in 30 days). Always previews first (dry_run=true) — set dry_run=false to actually delete.

    Args:
        name_contains: Delete workflows whose name contains this substring (case-insensitive)
        not_run_in_days: Delete workflows that haven't been run in this many days (0 = ignore)
        dry_run: If true (default), only preview what would be deleted. Set false to execute.
    """
    return json.dumps(_delete_workflows(name_contains, not_run_in_days, dry_run), indent=2, default=str)


@mcp_server.tool()
def mwaa_list_runs(name_contains: str = "", status: str = "", hours_back: int = 0) -> str:
    """List workflow runs across all (or filtered) workflows with status summary. Supports filtering by workflow name, run status (SUCCESS/FAILED/RUNNING/etc.), and time window (e.g. hours_back=24 for last day's runs).

    Args:
        name_contains: Optional filter for workflow names (case-insensitive)
        status: Optional filter for run status (SUCCESS, FAILED, RUNNING, QUEUED, STOPPED, TIMEOUT)
        hours_back: Only include runs from the last N hours (0 = all runs)
    """
    return json.dumps(_list_runs(name_contains, status, hours_back), indent=2, default=str)


@mcp_server.tool()
def mwaa_get_workflow_summary(workflow_name: str) -> str:
    """Compact workflow overview: name, status, task/operator counts, latest run result, run history stats. Much lighter than mwaa_get_workflow (no full YAML).

    Args:
        workflow_name: Workflow name (exact or partial match)
    """
    return json.dumps(_get_workflow_summary(workflow_name), indent=2, default=str)


@mcp_server.tool()
def mwaa_bulk_status(name_contains: str = "", names: str = "") -> str:
    """Get status of multiple workflows with their latest run result in one call. Filter by name substring or provide comma-separated workflow names.

    Args:
        name_contains: Filter workflows by name substring (e.g. 'neptune' or 'glue')
        names: Comma-separated list of workflow name substrings to match (e.g. 'neptune,glue,s3')
    """
    names_list = [n.strip() for n in names.split(",") if n.strip()] if names else None
    return json.dumps(_bulk_status(name_contains, names_list), indent=2, default=str)


@mcp_server.tool()
def mwaa_redeploy(workflow_name: str, yaml_content: str, s3_bucket: str = "", s3_key: str = "") -> str:
    """Update an existing workflow's YAML and start a new run. Reuses the existing S3 location and execution role. Lighter than deploy_and_run for iterating on an existing workflow.

    Args:
        workflow_name: Existing workflow name (exact or partial match)
        yaml_content: New DAG YAML content
        s3_bucket: Optional S3 bucket override (defaults to existing)
        s3_key: Optional S3 key override (defaults to existing)
    """
    return json.dumps(_redeploy_workflow(workflow_name, yaml_content, s3_bucket, s3_key), indent=2, default=str)


@mcp_server.tool()
def mwaa_compare_versions(workflow_name: str) -> str:
    """Compare the latest two versions of a workflow to see what changed in the YAML. Shows a unified diff and version metadata.

    Args:
        workflow_name: Workflow name (exact or partial match)
    """
    return json.dumps(_compare_versions(workflow_name), indent=2, default=str)


def handler(event, context):
    return mcp_server.handle_request(event, context)
