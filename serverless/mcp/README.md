# MWAA Serverless DAG Factory MCP Server

MCP server on AWS Lambda that helps AI agents build, validate, convert, deploy, and operate MWAA Serverless workflows.

## Deploy

```bash
sam build
sam deploy --guided
```

Accept the defaults during `--guided`. When it finishes, grab the `McpApiUrl` from the Outputs section.

## Connect to Kiro CLI

Create `.kiro/settings/mcp.json` in your project root (or `~/.kiro/settings/mcp.json` for global):

```json
{
  "mcpServers": {
    "mwaa-dag-factory": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://xxxxxxxx.execute-api.us-east-1.amazonaws.com/mcp"
      ]
    }
  }
}
```

Then restart Kiro CLI. All tools will be available automatically.

## Tools

### DAG Authoring

| Tool | Description |
|---|---|
| `generate_dag_yaml` | Generate YAML for a given AWS service (s3, glue, athena, bedrock, lambda, emr_serverless, emr, batch, step_functions, redshift, sns, sqs, ecs, eks, cloudformation, sagemaker, rds, ec2, eventbridge, comprehend, dms, kinesis_analytics, neptune, glacier, datasync, appflow, quicksight, dynamodb, opensearch_serverless) |
| `validate_dag_yaml` | Validate YAML against all MWAA Serverless constraints (operators, params, Jinja, limits) |
| `list_supported_operators` | List supported operators (short name + FQN), filterable by service |
| `get_serverless_constraints` | Get all constraints: Jinja vars/macros, DAG/task params, AWS base attrs, API actions |
| `get_serverless_overview` | Overview of MWAA Serverless: deployment model, prerequisites, CLI commands, authoring guidelines |
| `analyze_python_dag` | Analyze Python DAG source for compatibility issues (blockers, warnings, info) |
| `convert_python_to_yaml` | Convert a Python DAG to MWAA Serverless YAML via AST extraction with operator replacement |
| `generate_execution_role` | Generate IAM execution role policy and CLI commands scoped to the operators in a DAG |
| `get_service_tasks_tool` | Get task definitions for a single service as a reusable building block |
| `compose_dag_yaml_tool` | Compose multi-service DAGs with cross-service dependencies |

### Workflow Operations

| Tool | Description |
|---|---|
| `mwaa_list_workflows` | List workflows with optional name/status filters. Compact output. |
| `mwaa_get_workflow` | Get workflow details including DAG YAML, operators used, execution role, S3 location |
| `mwaa_get_workflow_summary` | Compact overview: status, task/operator counts, latest run, run history stats. No full YAML. |
| `mwaa_bulk_status` | Status of multiple workflows with latest run result in one call. Filter by name or comma-separated list. |
| `mwaa_start_run` | Start a workflow run by name |
| `mwaa_get_run_status` | Get run status with per-task details and error messages. Defaults to latest run. |
| `mwaa_list_runs` | List runs across workflows with status/time filters (e.g. "yesterday's runs", "all failed runs") |
| `mwaa_poll_run` | Poll a run until terminal state or timeout (25s). Returns `completed: false` if still running. |
| `mwaa_stop_run` | Stop a running workflow. Defaults to latest active run. |
| `mwaa_find_workflows_by_service` | Find workflows using a specific AWS service by inspecting actual DAG YAML definitions |
| `mwaa_deploy_and_run` | Upload YAML to S3, create/update workflow, and start a run — all in one call |
| `mwaa_redeploy` | Update an existing workflow's YAML and start a new run. Reuses existing S3 location and role. |
| `mwaa_delete_workflows` | Bulk delete by name pattern or inactivity period. Dry run by default. |
| `mwaa_get_failed_runs` | Scan workflows for recent failures, pull CloudWatch task logs, and analyze with Bedrock AI |
| `mwaa_compare_versions` | Diff the latest two versions of a workflow to see what changed in the YAML |

## Usage examples

| What you ask | What happens |
|---|---|
| "Create a Glue pipeline DAG" | `generate_dag_yaml` → `validate_dag_yaml` → `generate_execution_role` |
| "Convert this Python DAG to MWAA Serverless YAML" | `analyze_python_dag` → `convert_python_to_yaml` → `validate_dag_yaml` |
| "Deploy and test this DAG" | `validate_dag_yaml` → `mwaa_deploy_and_run` → `mwaa_poll_run` |
| "Which workflows use Step Functions?" | `mwaa_find_workflows_by_service` (inspects all DAG YAMLs) |
| "What failed in the last 24 hours?" | `mwaa_get_failed_runs` (scans all workflows, pulls logs, Bedrock analysis) |
| "Show me the status of my S3 workflow" | `mwaa_get_run_status` |
| "Stop the running Neptune workflow" | `mwaa_stop_run` |
| "List all my workflows" | `mwaa_list_workflows` |
| "Show me all of yesterday's runs" | `mwaa_list_runs` with `hours_back=24` |
| "Status of all neptune and glue workflows" | `mwaa_bulk_status` with `names="neptune,glue"` |
| "Delete workflows that start with test" | `mwaa_delete_workflows` with `name_contains="test"` (dry run first) |
| "Delete workflows not run in 30 days" | `mwaa_delete_workflows` with `not_run_in_days=30` |
| "What changed in the last deploy?" | `mwaa_compare_versions` (diffs latest two YAML versions) |
| "Update and rerun this workflow" | `mwaa_redeploy` (reuses existing S3 location and role) |
| "Quick summary of my SQS workflow" | `mwaa_get_workflow_summary` (no full YAML, just stats) |

### Create and deploy a DAG

1. Agent calls `generate_dag_yaml` for the target service
2. Agent calls `validate_dag_yaml` to check for errors
3. Agent calls `generate_execution_role` to produce IAM policy + CLI commands
4. Agent calls `mwaa_deploy_and_run` to upload, create, and start in one call
5. Agent calls `mwaa_poll_run` to wait for completion

### Diagnose failures

1. Agent calls `mwaa_get_failed_runs` — scans all workflows, pulls CloudWatch error logs, and sends to Bedrock for root cause analysis
2. Returns per-workflow failure details with specific error messages from task logs and AI-generated fix suggestions

### Convert a Python DAG

1. Agent calls `analyze_python_dag` to check compatibility
2. Agent calls `convert_python_to_yaml` to get the YAML and see what got replaced
3. Agent calls `validate_dag_yaml` on the final YAML to confirm it's clean

## YAML schema

The DAG YAML schema uses:
- Single DAG per file (DAG ID as root key)
- `tasks` as an **array** of task objects
- Each task requires `task_id` and `operator` (short name like `GlueJobOperator` or FQN)
- Operator-specific params go inside a `parameters` object
- Dependencies via `upstream_tasks` / `downstream_tasks` arrays
- Duration strings for `retry_delay` and `execution_timeout` (e.g. `5m`, `1h`)
- `EmptyOperator` supported for no-op/join tasks

```yaml
my_pipeline:
  schedule: "@daily"
  max_active_runs: 4
  tasks:
    - task_id: extract
      operator: S3ListOperator
      parameters:
        bucket: my-bucket
    - task_id: transform
      operator: GlueJobOperator
      retries: 2
      retry_delay: "5m"
      execution_timeout: "30m"
      parameters:
        job_name: my-job-{{ ds_nodash }}
      upstream_tasks:
        - extract
    - task_id: done
      operator: EmptyOperator
      upstream_tasks:
        - transform
```

## Constraints enforced

Per the [MWAA Serverless documentation](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/):

- Only [officially supported operators](https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/operators.html) from the Amazon Provider Package (+ EmptyOperator)
- DAG params validated: `dag_id`, `schedule`, `start_date`, `end_date`, `max_active_runs`, `max_active_tasks`
- Task params validated: `task_id`, `retries` (0–3), `retry_delay` (0–300s), `execution_timeout` (max 3600s)
- Jinja variables: `ds`, `ds_nodash`, `ts`, `ts_nodash`, `params`, `ti`/`task_instance`, `macros`
- Macros: `macros.datetime`, `macros.timedelta`, `macros.dateutil`, `macros.time`, `macros.uuid`, `macros.random`, `ds_add`, `ds_format`, `datetime_diff_for_humans`, `random`
- AWS base attrs: `aws_conn_id` controlled by service, `verify`/`botocore_config` not supported, `region_name` from environment
- No deferrable operators, dynamic task mapping, Python/Bash operators, decorated tasks/DAGs

## Architecture

```
serverless/
├── template.yaml           # SAM template (Lambda + API Gateway + IAM)
├── samconfig.toml          # SAM deploy config
├── README.md
└── src/
    ├── app.py              # Lambda MCP handler (25 tools)
    ├── tools.py            # Generate, validate, list, constraints, compose
    ├── operations.py       # Workflow ops: list, deploy, run, poll, logs, failures
    ├── schema.py           # Operator allowlist (short name → FQN)
    ├── constraints.py      # Jinja vars, macros, DAG/task params, API
    ├── python_analyzer.py  # AST compatibility analysis
    ├── python_converter.py # AST Python-to-YAML conversion
    └── requirements.txt    # PyYAML, awslabs.mcp_lambda_handler, boto3
```

## IAM permissions

The Lambda function requires these permissions (configured in `template.yaml`):

| Permission | Purpose |
|---|---|
| `airflow-serverless:ListWorkflows/GetWorkflow/CreateWorkflow/UpdateWorkflow/DeleteWorkflow` | Workflow management |
| `airflow-serverless:StartWorkflowRun/GetWorkflowRun/ListWorkflowRuns/StopWorkflowRun/ListWorkflowVersions` | Run management |
| `s3:GetObject/PutObject` | Read DAG definitions, upload new ones |
| `logs:DescribeLogGroups/DescribeLogStreams/GetLogEvents` | Pull CloudWatch task logs for failure analysis |
| `bedrock:InvokeModel` | AI-powered failure analysis via Claude |
| `iam:PassRole` | Pass execution role when creating workflows |
