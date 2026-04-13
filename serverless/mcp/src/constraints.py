"""
MWAA Serverless supported Jinja template variables, macros, DAG/task parameters,
and AWS base operator attributes.

Source: https://docs.aws.amazon.com/mwaa/latest/mwaa-serverless-userguide/
"""

# ── Supported Jinja template variables ──
SUPPORTED_JINJA_VARIABLES = {
    "macros", "task_instance", "ti", "params",
    "ds", "ds_nodash", "ts", "ts_nodash",
}

# ── Supported macros ──
SUPPORTED_MACROS = {
    "macros.datetime", "macros.timedelta", "macros.dateutil",
    "macros.time", "macros.uuid", "macros.random",
    "datetime_diff_for_humans", "ds_add", "ds_format", "random",
}

# ── DAG-level parameters validated by MWAA Serverless ──
VALIDATED_DAG_PARAMS = {
    "dag_id": "Must be a valid, non-empty string",
    "schedule": "Must be a valid CRON expression format",
    "start_date": "Must be in the future",
    "end_date": "Must be after or equal to start_date",
    "max_active_runs": "Must be smaller than account limit (default: 16)",
}

# ── DAG-level parameters ignored by MWAA Serverless ──
IGNORED_DAG_PARAMS = {
    "template_searchpath", "template_undefined", "user_defined_macros",
    "user_defined_filters", "catchup", "access_control",
    "jinja_environment_kwargs", "render_template_as_native_obj", "tags",
    "owner_links", "auto_register", "fail_fast", "dag_display_name",
    "depends_on_past", "email_on_failure", "email_on_retry", "description",
    "max_consecutive_failed_dag_runs", "dagrun_timeout", "sla_miss_callback",
    "on_failure_callback", "on_success_callback", "is_paused_upon_creation",
}

# ── Task-level parameters validated by MWAA Serverless ──
VALIDATED_TASK_PARAMS = {
    "task_id": "Must be a valid string",
    "retries": "Must be between 0 and 3 (default: 1)",
    "retry_delay": "Must be between 0 and 300 seconds (default: 300)",
    "execution_timeout": "Maximum 3600 seconds (default: 3600)",
}

# ── Task-level parameters ignored by MWAA Serverless ──
IGNORED_TASK_PARAMS = {
    "email_on_retry", "email_on_failure", "retry_exponential_backoff",
    "depends_on_past", "ignore_first_depends_on_past", "wait_for_downstream",
    "priority_weight", "sla", "max_active_tis_per_dag",
    "max_active_tis_per_dagrun", "task_concurrency", "resources",
    "run_as_user", "executor_config", "doc", "doc_md", "doc_rst",
    "doc_json", "doc_yaml", "task_display_name", "logger_name",
    "allow_nested_operators", "inlets", "outlets", "map_index_template",
    "email", "owner", "max_retry_delay", "on_execute_callback",
    "on_failure_callback", "on_success_callback", "on_retry_callback",
    "on_skipped_callback", "wait_for_past_depends_before_skipping",
    "do_xcom_push", "multiple_outputs", "start_date", "end_date",
    "weight_rule", "queue", "pool", "pool_slots", "pre_execute",
    "post_execute", "executor", "task_group",
}

# ── AWS base operator attributes ──
AWS_BASE_OPERATOR_ATTRS = {
    "aws_conn_id": "Controlled by service (do not set)",
    "verify": "Not supported",
    "botocore_config": "Not supported",
    "region_name": "Gets region from environment (do not set)",
}

# Features explicitly NOT supported
UNSUPPORTED_FEATURES = [
    "Deferrable operators (deferrable=True)",
    "Dynamic task mapping (.expand() / .map())",
    "PythonOperator / BashOperator / any non-Amazon provider operator",
    "Decorated tasks (@task, @task.python, @task.bash)",
    "Decorated DAGs (@dag)",
    "TaskFlow API",
    "aws_conn_id (controlled by service)",
    "verify / botocore_config / region_name on operators",
]

# ── MWAA Serverless API actions ──
# Service name: mwaa-serverless (NOT mwaa, which is classic/provisioned MWAA)
MWAA_API_ACTIONS = {
    "service_name": "mwaa-serverless",
    "cli_prefix": "aws mwaa-serverless",
    "workflow_management": {
        "actions": [
            "CreateWorkflow",
            "DeleteWorkflow",
            "GetWorkflow",
            "ListWorkflows",
            "ListWorkflowVersions",
            "UpdateWorkflow",
            "StartWorkflowRun",
            "StopWorkflowRun",
            "ListTagsForResource",
            "TagResource",
            "UntagResource",
        ],
    },
}

# ── Service overview (educates the LLM about how MWAA Serverless works) ──
SERVICE_OVERVIEW = {
    "what_is_mwaa_serverless": (
        "Amazon MWAA Serverless is a serverless deployment option for MWAA that "
        "eliminates managing Apache Airflow environments. It uses YAML-based "
        "workflow definitions (not Python DAGs), automatic scaling, pay-per-use "
        "pricing, and per-workflow IAM execution role isolation. It uses Apache "
        "Airflow v3 with Python 3.12."
    ),
    "how_it_differs_from_classic_mwaa": {
        "service_name": "mwaa-serverless (NOT mwaa)",
        "no_environments": "There are no 'environments' to create or manage. The unit of deployment is a 'workflow'.",
        "no_airflow_ui": "No direct Airflow UI access. Monitoring is via CloudWatch logs and the console.",
        "yaml_only": "Workflows are defined in YAML (DAG factory format), not Python.",
        "per_workflow_isolation": "Each workflow has its own IAM execution role and isolated compute.",
        "pay_per_use": "You only pay for actual workflow run time, no idle infrastructure costs.",
    },
    "dag_authoring_guidelines": {
        "provisioning_with_cloudformation": (
            "When a DAG needs AWS resources for testing (e.g., SQS queues, SNS topics, "
            "Lambda functions, Step Functions state machines, IAM roles for those services, "
            "S3 buckets, Athena databases, Glue databases, VPCs, etc.), use "
            "CloudFormationCreateStackOperator with an inline CloudFormation template in the "
            "'TemplateBody' parameter (as a YAML text block). This makes DAGs FULLY SELF-CONTAINED "
            "so they can run without any pre-existing infrastructure. Pair it with "
            "CloudFormationDeleteStackOperator for cleanup. The generate_dag_yaml tool templates "
            "follow this pattern: they provision all prerequisite resources via CloudFormation "
            "at the start, run the actual service operations, then tear everything down."
        ),
        "always_clean_up": (
            "DAGs should ALWAYS clean up any resources they create, unless the user explicitly "
            "says otherwise. For CloudFormation-provisioned resources, add a "
            "CloudFormationDeleteStackOperator at the end. For S3 objects, use "
            "S3DeleteObjectsOperator then S3DeleteBucketOperator. CRITICAL: All cleanup tasks "
            "MUST set 'trigger_rule: all_done' so they run regardless of whether upstream tasks "
            "succeed or fail. This prevents resource leaks on DAG failure."
        ),
        "use_params_with_defaults": (
            "Always use '{{ params.X }}' Jinja references for configurable values (bucket names, "
            "role ARNs, database names, job names, etc.). Always provide working default values "
            "in the DAG-level 'params' section. Use unique values where appropriate (e.g., include "
            "a random suffix like '{{ macros.uuid.uuid4().hex[:8] }}' in resource names, or use "
            "descriptive defaults like 'mwaa-demo-bucket-<unique>' that the user should replace)."
        ),
    },
    "workflow_when_user_says_create_dag": {
        "description": (
            "When the user asks to CREATE a DAG, follow ALL of these steps in order:"
        ),
        "step_1": "Call generate_dag_yaml to produce the YAML.",
        "step_2": "Call validate_dag_yaml on the generated YAML to check for errors.",
        "step_3": (
            "Call generate_execution_role with the YAML to produce a permissive IAM "
            "execution role and policy scoped to the operators in the DAG. The role "
            "trusts airflow-serverless.amazonaws.com and includes CloudWatch Logs, "
            "IAM PassRole, and all service-specific permissions detected from the operators."
        ),
        "step_4": (
            "Present the user with: (a) the YAML, (b) the IAM trust policy and permissions "
            "policy, (c) ready-to-run AWS CLI commands to create the role, attach the policy, "
            "upload the YAML to S3, create the workflow, and start a run."
        ),
    },
    "workflow_when_user_says_test_dag": {
        "description": (
            "When the user asks to TEST a DAG, follow ALL of these steps in order. "
            "The goal is end-to-end: generate, validate, deploy, execute, and surface any failures."
        ),
        "step_1": "Call generate_dag_yaml to produce the YAML.",
        "step_2": (
            "Call validate_dag_yaml on the generated YAML. If validation returns errors, "
            "fix them and re-validate before proceeding. Show the user any warnings."
        ),
        "step_3": (
            "Call generate_execution_role with the YAML to produce a permissive IAM "
            "execution role and policy. Execute the AWS CLI commands to create the role "
            "and attach the policy (or confirm the role already exists)."
        ),
        "step_4": (
            "Upload the YAML to the S3 bucket using: "
            "aws s3 cp <local-file> s3://<bucket>/<key>"
        ),
        "step_5": (
            "Create or update the workflow using: "
            "aws mwaa-serverless create-workflow --name <name> "
            "--definition-s3-location '{\"Bucket\": \"<bucket>\", \"ObjectKey\": \"<key>\"}' "
            "--execution-role-arn <role-arn>. "
            "If the workflow already exists, use update-workflow instead."
        ),
        "step_6": (
            "Start a workflow run using: "
            "aws mwaa-serverless start-workflow-run --workflow-arn <arn>"
        ),
        "step_7": (
            "Poll the workflow run status using: "
            "aws mwaa-serverless get-workflow --workflow-arn <arn> "
            "until the run reaches a terminal state (SUCCESS, FAILED, TIMEOUT). "
            "If the run FAILS, surface the failure reason and any error details to the user. "
            "Check CloudWatch Logs for task-level errors if available."
        ),
    },
    "deployment_workflow": {
        "step_1_s3_bucket": (
            "Create an S3 bucket (same region, block all public access, versioning enabled) "
            "to store your YAML workflow definition files."
        ),
        "step_2_execution_role": (
            "Create an IAM execution role with trust policy for "
            "'airflow-serverless.amazonaws.com'. The role needs permissions for "
            "CloudWatch Logs (logs:CreateLogStream, logs:PutLogEvents), and "
            "whatever AWS services your workflow tasks use (S3, Glue, Athena, etc.). "
            "Optional: KMS permissions if using a customer-managed key."
        ),
        "step_3_upload_yaml": "Upload your YAML workflow definition file to the S3 bucket.",
        "step_4_create_workflow": (
            "aws mwaa-serverless create-workflow "
            "--name <workflow-name> "
            "--definition-s3-location '{\"Bucket\": \"<bucket>\", \"ObjectKey\": \"<key>\"}' "
            "--execution-role-arn <role-arn>"
        ),
        "step_5_run_workflow": (
            "aws mwaa-serverless start-workflow-run "
            "--workflow-arn <workflow-arn>"
        ),
        "step_6_monitor": (
            "aws mwaa-serverless get-workflow --workflow-arn <workflow-arn> "
            "to check status. Workflow run states: STARTING, QUEUED, RUNNING, "
            "SUCCESS, FAILED, TIMEOUT, STOPPING, STOPPED."
        ),
    },
    "workflow_types": {
        "scheduled": "Runs on the schedule defined in the YAML. Can also be run on-demand.",
        "manual_only": "Ignores any schedule, can only be run on-demand via StartWorkflowRun.",
        "disabled": "Cannot be run on schedule or on-demand.",
    },
    "execution_role_trust_policy": {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "airflow-serverless.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    },
    "prerequisites": [
        "AWS account with mwaa-serverless permissions (airflow-serverless:* actions)",
        "S3 bucket (same region, block public access, versioning enabled)",
        "IAM execution role trusting airflow-serverless.amazonaws.com",
        "AWS CLI configured (verify with: aws mwaa-serverless help)",
    ],
    "available_regions": [
        "us-east-1", "us-east-2", "us-west-1", "us-west-2",
        "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
        "eu-south-2", "eu-central-2",
        "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
        "ap-south-1", "ap-southeast-1", "ap-southeast-2", "ap-southeast-5", "ap-southeast-7",
        "ap-east-1",
        "ca-central-1", "sa-east-1", "af-south-1",
    ],
}
