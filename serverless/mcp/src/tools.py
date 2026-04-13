"""YAML generation and validation for MWAA Serverless DAG factory definitions."""

import re
import yaml
from schema import SUPPORTED_OPERATORS, ALLOWED_OPERATOR_VALUES
from constraints import (
    SUPPORTED_JINJA_VARIABLES, SUPPORTED_MACROS,
    VALIDATED_DAG_PARAMS, IGNORED_DAG_PARAMS,
    VALIDATED_TASK_PARAMS, IGNORED_TASK_PARAMS,
    AWS_BASE_OPERATOR_ATTRS, UNSUPPORTED_FEATURES,
    MWAA_API_ACTIONS, SERVICE_OVERVIEW,
)

_JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)")
_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_TASK_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_DAG_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

_DURATION_MULTIPLIERS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def _parse_duration_seconds(val):
    """Parse a duration value to seconds. Accepts int or string like '5m'."""
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        m = _DURATION_RE.match(val)
        if m:
            return int(m.group(1)) * _DURATION_MULTIPLIERS[m.group(2)]
    return None


def validate_yaml(yaml_content: str) -> dict:
    """Validate a DAG factory YAML against the MWAA Serverless YAML schema."""
    errors = []
    warnings = []

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return {"valid": False, "errors": [f"YAML parse error: {e}"], "warnings": []}

    if not isinstance(data, dict):
        return {"valid": False, "errors": ["Root must be a YAML mapping"], "warnings": []}

    if len(data) > 1:
        warnings.append("Schema allows maxProperties: 1 at root (single DAG per file)")

    for dag_key, dag_cfg in data.items():
        if not _DAG_ID_RE.match(dag_key):
            errors.append(f"DAG key '{dag_key}' must match ^[a-zA-Z0-9_-]+$")

        if not isinstance(dag_cfg, dict):
            errors.append(f"'{dag_key}' must be a mapping")
            continue

        if "tasks" not in dag_cfg:
            errors.append(f"'{dag_key}' missing required field 'tasks'")
            continue

        # DAG-level param checks
        for key in dag_cfg:
            if key in ("tasks", "params", "default_args", "description", "schedule",
                       "start_date", "end_date", "max_active_runs", "max_active_tasks", "dag_id"):
                continue
            if key in IGNORED_DAG_PARAMS:
                warnings.append(f"DAG '{dag_key}': '{key}' is ignored by MWAA Serverless")
            else:
                warnings.append(f"DAG '{dag_key}': unknown DAG-level param '{key}'")

        mar = dag_cfg.get("max_active_runs")
        if mar is not None and (not isinstance(mar, int) or mar < 1):
            errors.append(f"DAG '{dag_key}': max_active_runs must be integer >= 1")

        mat = dag_cfg.get("max_active_tasks")
        if mat is not None and (not isinstance(mat, int) or mat < 1):
            errors.append(f"DAG '{dag_key}': max_active_tasks must be integer >= 1")

        # default_args validation
        da = dag_cfg.get("default_args", {})
        if isinstance(da, dict):
            da_retries = da.get("retries")
            if da_retries is not None and (not isinstance(da_retries, int) or da_retries < 0):
                errors.append(f"DAG '{dag_key}': default_args.retries must be integer >= 0")
            da_rd = da.get("retry_delay")
            if da_rd is not None and _parse_duration_seconds(da_rd) is None:
                errors.append(f"DAG '{dag_key}': default_args.retry_delay must match pattern ^\\d+[smhd]$")
            da_et = da.get("execution_timeout")
            if da_et is not None and _parse_duration_seconds(da_et) is None:
                errors.append(f"DAG '{dag_key}': default_args.execution_timeout must match pattern ^\\d+[smhd]$")

        # Params validation
        params = dag_cfg.get("params")
        if params is not None and not isinstance(params, dict):
            errors.append(f"DAG '{dag_key}': 'params' must be a mapping, got {type(params).__name__}")

        # Tasks validation — schema says tasks is an array
        tasks = dag_cfg["tasks"]
        if isinstance(tasks, list):
            _validate_task_list(tasks, dag_key, errors, warnings)
        elif isinstance(tasks, dict):
            # Also accept dict format for backward compat with earlier examples
            _validate_task_dict(tasks, dag_key, errors, warnings)
        else:
            errors.append(f"'{dag_key}' tasks must be an array or mapping")

    _check_jinja_refs(data, warnings)
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _validate_task_list(tasks, dag_key, errors, warnings):
    """Validate tasks as array (per the YAML schema)."""
    task_ids = set()
    for i, task_cfg in enumerate(tasks):
        if not isinstance(task_cfg, dict):
            errors.append(f"DAG '{dag_key}' task[{i}] must be a mapping")
            continue
        tid = task_cfg.get("task_id")
        if not tid:
            errors.append(f"DAG '{dag_key}' task[{i}] missing 'task_id'")
        elif not _TASK_ID_RE.match(tid):
            errors.append(f"Task '{tid}': task_id must match ^[a-zA-Z0-9_-]+$")
        else:
            task_ids.add(tid)

    for task_cfg in tasks:
        if not isinstance(task_cfg, dict):
            continue
        tid = task_cfg.get("task_id", f"task[?]")
        _validate_task_common(task_cfg, tid, dag_key, task_ids, errors, warnings)


def _validate_task_dict(tasks, dag_key, errors, warnings):
    """Validate tasks as dict (backward compat)."""
    task_ids = set(tasks.keys())
    for task_name, task_cfg in tasks.items():
        if not isinstance(task_cfg, dict):
            errors.append(f"Task '{task_name}' in '{dag_key}' must be a mapping")
            continue
        tid = task_cfg.get("task_id", task_name)
        _validate_task_common(task_cfg, tid, dag_key, task_ids, errors, warnings)


def _validate_task_common(task_cfg, tid, dag_key, task_ids, errors, warnings):
    """Validate a single task against all constraints."""
    op = task_cfg.get("operator")
    if not op:
        errors.append(f"Task '{tid}' missing 'operator'")
        return

    if op not in ALLOWED_OPERATOR_VALUES:
        errors.append(f"Task '{tid}': operator '{op}' not in supported operators list.")
        return

    # Deferrable
    if task_cfg.get("deferrable"):
        errors.append(f"Task '{tid}': deferrable=True not supported.")

    # Dynamic mapping
    if "expand" in task_cfg or "map" in task_cfg:
        errors.append(f"Task '{tid}': dynamic task mapping not supported.")

    # AWS base attrs (check both top-level and inside parameters)
    for scope in (task_cfg, task_cfg.get("parameters", {})):
        if not isinstance(scope, dict):
            continue
        for attr, msg in AWS_BASE_OPERATOR_ATTRS.items():
            if attr in scope:
                if "Not supported" in msg:
                    errors.append(f"Task '{tid}': '{attr}' is {msg} in MWAA Serverless.")
                elif attr == "aws_conn_id":
                    warnings.append(f"Task '{tid}': aws_conn_id is controlled by service.")
                elif attr == "region_name":
                    warnings.append(f"Task '{tid}': region_name is set from environment.")

    # Task-level validated params
    retries = task_cfg.get("retries")
    if retries is not None and (not isinstance(retries, int) or retries < 0 or retries > 3):
        errors.append(f"Task '{tid}': retries must be 0-3 (got {retries})")

    rd = task_cfg.get("retry_delay")
    if rd is not None:
        rd_s = _parse_duration_seconds(rd)
        if rd_s is None:
            errors.append(f"Task '{tid}': retry_delay must be int or match ^\\d+[smhd]$")
        elif rd_s < 0 or rd_s > 300:
            errors.append(f"Task '{tid}': retry_delay must be 0-300 seconds (got {rd_s}s)")

    et = task_cfg.get("execution_timeout")
    if et is not None:
        et_s = _parse_duration_seconds(et)
        if et_s is None:
            errors.append(f"Task '{tid}': execution_timeout must be int or match ^\\d+[smhd]$")
        elif et_s > 3600:
            errors.append(f"Task '{tid}': execution_timeout max 3600 seconds (got {et_s}s)")

    # Ignored task params
    for key in task_cfg:
        if key in IGNORED_TASK_PARAMS:
            warnings.append(f"Task '{tid}': '{key}' is ignored by MWAA Serverless")

    # Dependency refs (upstream_tasks / downstream_tasks / dependencies)
    for dep_key in ("upstream_tasks", "downstream_tasks", "dependencies"):
        for dep in task_cfg.get(dep_key, []):
            if dep not in task_ids:
                errors.append(f"Task '{tid}': {dep_key} references '{dep}' which doesn't exist in '{dag_key}'")


def _check_jinja_refs(data, warnings):
    strings = []
    _collect_strings(data, strings)
    for s in strings:
        for match in _JINJA_VAR_RE.finditer(s):
            var = match.group(1)
            root = var.split(".")[0]
            if root in SUPPORTED_JINJA_VARIABLES or root in ("ti", "task_instance", "macros"):
                continue
            if var in SUPPORTED_MACROS:
                continue
            warnings.append(f"Jinja '{{{{ {var} }}}}' may not be supported. Supported vars: {', '.join(sorted(SUPPORTED_JINJA_VARIABLES))}")


def _collect_strings(obj, result):
    if isinstance(obj, str):
        result.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, result)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, result)


def generate_yaml(dag_id, service, description="", schedule="None", params=None):
    """Generate a DAG factory YAML using the dict-based task schema matching official examples."""
    templates = _get_service_templates()
    svc = service.lower().replace(" ", "_")
    if svc not in templates:
        return f"Unknown service '{service}'. Available: {', '.join(sorted(templates.keys()))}"

    t = templates[svc]
    tasks = _resolve_operator_fqns(t["tasks"])
    tasks = _normalize_tasks_to_dict(tasks)
    dag = {dag_id: {"schedule": schedule, "tasks": tasks}}
    # Apply extra fields (dag_id, default_args, etc.)
    for k, v in t.get("extra_fields", {}).items():
        dag[dag_id][k] = v
    if description:
        dag[dag_id]["description"] = description
    if params:
        dag[dag_id]["params"] = params
    elif t.get("default_params"):
        dag[dag_id]["params"] = t["default_params"]
    return yaml.dump(dag, default_flow_style=False, sort_keys=False)


def _normalize_tasks_to_dict(tasks):
    """Convert list-format tasks to dict-format and flatten 'parameters' into task body."""
    if isinstance(tasks, dict):
        # Already dict format — just flatten any nested 'parameters'
        for tid, tcfg in tasks.items():
            _flatten_parameters(tcfg)
        return tasks
    if not isinstance(tasks, list):
        return tasks
    result = {}
    for tcfg in tasks:
        tid = tcfg.get("task_id", "unknown")
        _flatten_parameters(tcfg)
        # Convert upstream_tasks to dependencies
        if "upstream_tasks" in tcfg:
            tcfg["dependencies"] = tcfg.pop("upstream_tasks")
        if "downstream_tasks" in tcfg:
            del tcfg["downstream_tasks"]
        result[tid] = tcfg
    return result


def _flatten_parameters(tcfg):
    """Move contents of 'parameters' dict to top level of task config."""
    params = tcfg.pop("parameters", None)
    if isinstance(params, dict):
        for k, v in params.items():
            if k not in tcfg:
                tcfg[k] = v


def _resolve_operator_fqns(tasks):
    """Replace short operator names with fully qualified names."""
    import copy
    resolved = copy.deepcopy(tasks)
    if isinstance(resolved, dict):
        for tcfg in resolved.values():
            op = tcfg.get("operator", "")
            if op in SUPPORTED_OPERATORS:
                tcfg["operator"] = SUPPORTED_OPERATORS[op]
    elif isinstance(resolved, list):
        for tcfg in resolved:
            op = tcfg.get("operator", "")
            if op in SUPPORTED_OPERATORS:
                tcfg["operator"] = SUPPORTED_OPERATORS[op]
    return resolved


def list_operators(service_filter=""):
    filt = service_filter.lower()
    return [{"name": k, "fqn": v} for k, v in SUPPORTED_OPERATORS.items() if not filt or filt in k.lower() or filt in v.lower()]


def get_service_tasks(service):
    """Return the task definitions for a single service as a reusable block."""
    templates = _get_service_templates()
    svc = service.lower().replace(" ", "_")
    if svc not in templates:
        return {"error": f"Unknown service '{service}'. Available: {', '.join(sorted(templates.keys()))}"}
    t = templates[svc]
    tasks = _resolve_operator_fqns(t["tasks"])
    tasks = _normalize_tasks_to_dict(tasks)
    return {
        "service": svc,
        "tasks": tasks,
        "default_params": t.get("default_params", {}),
    }


def compose_dag_yaml(dag_id, services_config, description="", schedule="None", params=None):
    """Compose a multi-service DAG from service task blocks with custom dependencies.

    services_config is a list of dicts:
      [
        {"service": "s3", "task_prefix": "s3", "depends_on": []},
        {"service": "glue", "task_prefix": "glue", "depends_on": ["s3"]},
      ]

    Each service's tasks are prefixed to avoid ID collisions. Dependencies between
    services are wired by connecting the last non-cleanup task of the upstream service
    to the first task of the downstream service.
    """
    import copy
    templates = _get_service_templates()
    all_tasks = {}
    all_params = {}
    service_task_ids = {}  # prefix -> [ordered task_ids]
    service_first_task = {}  # prefix -> first task_id
    service_last_work_task = {}  # prefix -> last non-cleanup task_id

    for cfg in services_config:
        svc = cfg["service"].lower().replace(" ", "_")
        prefix = cfg.get("task_prefix", svc).replace("-", "_")
        depends_on = cfg.get("depends_on", [])

        if svc not in templates:
            return f"Unknown service '{svc}'. Available: {', '.join(sorted(templates.keys()))}"

        t = templates[svc]
        tasks = _resolve_operator_fqns(t["tasks"])
        tasks = _normalize_tasks_to_dict(tasks)

        # Prefix all task IDs and rewrite dependency references
        old_to_new = {}
        ordered_ids = []
        for tid in tasks:
            new_tid = f"{prefix}_{tid}"
            old_to_new[tid] = new_tid
            ordered_ids.append(new_tid)

        prefixed_tasks = {}
        for tid, tcfg in tasks.items():
            new_tid = old_to_new[tid]
            new_tcfg = copy.deepcopy(tcfg)
            new_tcfg["task_id"] = new_tid
            # Rewrite dependencies
            if "dependencies" in new_tcfg:
                new_tcfg["dependencies"] = [old_to_new.get(d, d) for d in new_tcfg["dependencies"]]
            prefixed_tasks[new_tid] = new_tcfg

        service_task_ids[prefix] = ordered_ids
        service_first_task[prefix] = ordered_ids[0] if ordered_ids else None

        # Find last non-cleanup task (not trigger_rule: all_done)
        last_work = ordered_ids[0] if ordered_ids else None
        for new_tid in ordered_ids:
            if prefixed_tasks[new_tid].get("trigger_rule") == "all_done":
                break
            last_work = new_tid
        service_last_work_task[prefix] = last_work

        # Wire cross-service dependencies
        if depends_on and service_first_task[prefix]:
            first_task = prefixed_tasks[service_first_task[prefix]]
            deps = first_task.get("dependencies", [])
            for upstream_prefix in depends_on:
                up = upstream_prefix.replace("-", "_")
                if up in service_last_work_task and service_last_work_task[up]:
                    deps.append(service_last_work_task[up])
            if deps:
                first_task["dependencies"] = deps

        all_tasks.update(prefixed_tasks)

        # Merge params with prefix
        for k, v in t.get("default_params", {}).items():
            all_params[f"{prefix}_{k}"] = v

        # Rewrite param references in task values
        for new_tid, tcfg in prefixed_tasks.items():
            _rewrite_param_refs(tcfg, prefix)

    # Build DAG
    dag = {dag_id: {"schedule": schedule, "tasks": all_tasks}}
    if description:
        dag[dag_id]["description"] = description
    merged_params = {**(params or {})}
    for k, v in all_params.items():
        if k not in merged_params:
            merged_params[k] = v
    if merged_params:
        dag[dag_id]["params"] = merged_params

    return yaml.dump(dag, default_flow_style=False, sort_keys=False)


def _rewrite_param_refs(obj, prefix):
    """Rewrite {{ params.X }} references to {{ params.prefix_X }} in all string values."""
    import re
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and "{{ params." in v:
                obj[k] = re.sub(r"\{\{\s*params\.(\w+)\s*\}\}", r"{{ params." + prefix + r"_\1 }}", v)
            else:
                _rewrite_param_refs(v, prefix)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str) and "{{ params." in v:
                obj[i] = re.sub(r"\{\{\s*params\.(\w+)\s*\}\}", r"{{ params." + prefix + r"_\1 }}", v)
            else:
                _rewrite_param_refs(v, prefix)


def list_unsupported():
    return UNSUPPORTED_FEATURES


def get_constraints():
    return {
        "supported_jinja_variables": sorted(SUPPORTED_JINJA_VARIABLES),
        "supported_macros": sorted(SUPPORTED_MACROS),
        "validated_dag_params": VALIDATED_DAG_PARAMS,
        "ignored_dag_params": sorted(IGNORED_DAG_PARAMS),
        "validated_task_params": VALIDATED_TASK_PARAMS,
        "ignored_task_params": sorted(IGNORED_TASK_PARAMS),
        "aws_base_operator_attrs": AWS_BASE_OPERATOR_ATTRS,
        "unsupported_features": UNSUPPORTED_FEATURES,
        "mwaa_api_actions": MWAA_API_ACTIONS,
    }


def get_overview():
    return SERVICE_OVERVIEW


# ── Operator FQN to IAM service/action mapping ──
_OPERATOR_IAM_MAP = {
    "s3": {"actions": ["s3:*"], "resource": "*"},
    "glue": {"actions": ["glue:*"], "resource": "*"},
    "glue_databrew": {"actions": ["databrew:*"], "resource": "*"},
    "glue_crawler": {"actions": ["glue:*"], "resource": "*"},
    "athena": {"actions": ["athena:*", "s3:*", "glue:*"], "resource": "*"},
    "bedrock": {"actions": ["bedrock:*"], "resource": "*"},
    "lambda_function": {"actions": ["lambda:*"], "resource": "*"},
    "step_function": {"actions": ["states:*"], "resource": "*"},
    "emr": {"actions": ["elasticmapreduce:*", "ec2:*"], "resource": "*"},
    "batch": {"actions": ["batch:*"], "resource": "*"},
    "ecs": {"actions": ["ecs:*", "ec2:*"], "resource": "*"},
    "eks": {"actions": ["eks:*", "ec2:*"], "resource": "*"},
    "cloud_formation": {"actions": ["cloudformation:*", "iam:*"], "resource": "*"},
    "sagemaker": {"actions": ["sagemaker:*"], "resource": "*"},
    "sagemaker_unified_studio": {"actions": ["sagemaker:*"], "resource": "*"},
    "rds": {"actions": ["rds:*"], "resource": "*"},
    "redshift_cluster": {"actions": ["redshift:*"], "resource": "*"},
    "redshift_data": {"actions": ["redshift-data:*", "redshift-serverless:*"], "resource": "*"},
    "dms": {"actions": ["dms:*"], "resource": "*"},
    "ec2": {"actions": ["ec2:*"], "resource": "*"},
    "sns": {"actions": ["sns:*"], "resource": "*"},
    "sqs": {"actions": ["sqs:*"], "resource": "*"},
    "eventbridge": {"actions": ["events:*"], "resource": "*"},
    "comprehend": {"actions": ["comprehend:*"], "resource": "*"},
    "kinesis_analytics": {"actions": ["kinesisanalytics:*"], "resource": "*"},
    "neptune": {"actions": ["neptune-db:*", "rds:*"], "resource": "*"},
    "glacier": {"actions": ["glacier:*"], "resource": "*"},
    "datasync": {"actions": ["datasync:*"], "resource": "*"},
    "appflow": {"actions": ["appflow:*"], "resource": "*"},
    "quicksight": {"actions": ["quicksight:*"], "resource": "*"},
    "dynamodb": {"actions": ["dynamodb:*"], "resource": "*"},
    "opensearch_serverless": {"actions": ["aoss:*"], "resource": "*"},
}


def generate_execution_role_policy(yaml_content):
    """Generate an IAM execution role policy and CLI commands for a given DAG YAML."""
    import json as _json
    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return {"error": f"YAML parse error: {e}"}

    if not isinstance(data, dict):
        return {"error": "Root must be a YAML mapping"}

    # Collect all operator FQNs from the DAG
    all_actions = set()
    operator_services = set()
    _extract_operators(data, operator_services)

    for svc in operator_services:
        if svc in _OPERATOR_IAM_MAP:
            all_actions.update(_OPERATOR_IAM_MAP[svc]["actions"])

    # Always include CloudWatch Logs and IAM PassRole
    statements = [
        {
            "Sid": "CloudWatchLogsAccess",
            "Effect": "Allow",
            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
            "Resource": "*",
        },
        {
            "Sid": "IAMPassRoleAccess",
            "Effect": "Allow",
            "Action": ["iam:PassRole", "iam:GetRole"],
            "Resource": "*",
        },
    ]

    if all_actions:
        statements.append({
            "Sid": "OperatorPermissions",
            "Effect": "Allow",
            "Action": sorted(all_actions),
            "Resource": "*",
        })

    policy = {"Version": "2012-10-17", "Statement": statements}
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "airflow-serverless.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    dag_id = list(data.keys())[0]
    role_name = f"mwaa-serverless-{dag_id}-role"

    return {
        "role_name": role_name,
        "trust_policy": trust_policy,
        "permissions_policy": policy,
        "detected_services": sorted(operator_services),
        "cli_commands": {
            "create_role": f"aws iam create-role --role-name {role_name} --assume-role-policy-document '{_json.dumps(trust_policy)}'",
            "put_policy": f"aws iam put-role-policy --role-name {role_name} --policy-name {dag_id}-policy --policy-document '{_json.dumps(policy)}'",
            "get_role_arn": f"aws iam get-role --role-name {role_name} --query 'Role.Arn' --output text",
        },
        "note": "This is a permissive testing policy. For production, scope down to least-privilege.",
    }


def _extract_operators(obj, services):
    """Walk a DAG YAML and extract operator service modules."""
    if isinstance(obj, dict):
        op = obj.get("operator", "")
        if isinstance(op, str) and op:
            # Extract service module from FQN or short name
            if "." in op:
                # FQN like airflow.providers.amazon.aws.operators.s3.S3CreateBucketOperator
                parts = op.split(".")
                for i, p in enumerate(parts):
                    if p in ("operators", "sensors") and i + 1 < len(parts):
                        services.add(parts[i + 1])
                        break
            else:
                # Short name — look up FQN
                if op in SUPPORTED_OPERATORS:
                    fqn = SUPPORTED_OPERATORS[op]
                    parts = fqn.split(".")
                    for i, p in enumerate(parts):
                        if p in ("operators", "sensors") and i + 1 < len(parts):
                            services.add(parts[i + 1])
                            break
        for v in obj.values():
            _extract_operators(v, services)
    elif isinstance(obj, list):
        for v in obj:
            _extract_operators(v, services)


def _get_service_templates():
    """Templates using the array-based task schema with short operator names."""
    return {
        "s3": {
            "default_params": {"bucket_name": "mwaa-test-s3"},
            "extra_fields": {"dag_id": "s3_dag", "default_args": {"start_date": "2024-01-01"}},
            "tasks": {
                "create_test_bucket": {
                    "operator": "S3CreateBucketOperator",
                    "bucket_name": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "task_id": "create_test_bucket",
                },
                "create_test_object": {
                    "operator": "S3CreateObjectOperator",
                    "data": "Hello World",
                    "s3_bucket": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "s3_key": "test-file.txt",
                    "task_id": "create_test_object",
                    "replace": True,
                    "dependencies": ["create_test_bucket"],
                },
                "wait_for_key": {
                    "operator": "S3KeySensor",
                    "bucket_key": "test-file.txt",
                    "bucket_name": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "task_id": "wait_for_key",
                    "use_regex": False,
                    "wildcard_match": False,
                    "dependencies": ["create_test_object"],
                },
                "list_objects": {
                    "operator": "S3ListOperator",
                    "apply_wildcard": False,
                    "bucket": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "delimiter": "",
                    "task_id": "list_objects",
                    "dependencies": ["wait_for_key"],
                },
                "delete_objects": {
                    "operator": "S3DeleteObjectsOperator",
                    "bucket": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "keys": ["test-file.txt"],
                    "task_id": "delete_objects",
                    "dependencies": ["list_objects"],
                },
                "delete_test_bucket": {
                    "operator": "S3DeleteBucketOperator",
                    "aws_conn_id": "aws_default",
                    "bucket_name": "{{ params.bucket_name }}-{{ ds_nodash }}",
                    "force_delete": True,
                    "task_id": "delete_test_bucket",
                    "trigger_rule": "all_done",
                    "dependencies": ["delete_objects"],
                },
            },
        },
        "glue": {
            "default_params": {"stack_name": "mwaa-test-glue-stack", "script_key": "scripts/glue-sample-job.py"},
            "extra_fields": {"dag_id": "glue_dag", "default_args": {"start_date": "2024-01-01"}},
            "tasks": {
                "create_glue_stack": {
                    "operator": "CloudFormationCreateStackOperator",
                    "stack_name": "{{ params.stack_name }}",
                    "cloudformation_parameters": {
                        "StackName": "{{ params.stack_name }}",
                        "Capabilities": ["CAPABILITY_IAM"],
                        "TemplateBody": (
                            "AWSTemplateFormatVersion: '2010-09-09'\n"
                            "Resources:\n"
                            "  ScriptBucket:\n"
                            "    Type: AWS::S3::Bucket\n"
                            "  GlueRole:\n"
                            "    Type: AWS::IAM::Role\n"
                            "    Properties:\n"
                            "      AssumeRolePolicyDocument:\n"
                            "        Version: '2012-10-17'\n"
                            "        Statement:\n"
                            "          - Effect: Allow\n"
                            "            Principal:\n"
                            "              Service: glue.amazonaws.com\n"
                            "            Action: sts:AssumeRole\n"
                            "      ManagedPolicyArns:\n"
                            "        - arn:aws:iam::aws:policy/service-role/AWSGlueServiceRole\n"
                            "      Policies:\n"
                            "        - PolicyName: S3Access\n"
                            "          PolicyDocument:\n"
                            "            Version: '2012-10-17'\n"
                            "            Statement:\n"
                            "              - Effect: Allow\n"
                            "                Action: s3:*\n"
                            "                Resource: '*'\n"
                            "Outputs:\n"
                            "  BucketName:\n"
                            "    Value: !Ref ScriptBucket\n"
                            "  RoleName:\n"
                            "    Value: !Ref GlueRole\n"
                        ),
                    },
                    "task_id": "create_glue_stack",
                },
                "wait_for_glue_stack": {
                    "operator": "CloudFormationCreateStackSensor",
                    "stack_name": "{{ params.stack_name }}",
                    "task_id": "wait_for_glue_stack",
                    "dependencies": ["create_glue_stack"],
                },
                "create_script": {
                    "operator": "S3CreateObjectOperator",
                    "data": (
                        "#!/usr/bin/env python3\n"
                        "import sys\n"
                        "from awsglue.transforms import *\n"
                        "from awsglue.utils import getResolvedOptions\n"
                        "from pyspark.context import SparkContext\n"
                        "from awsglue.context import GlueContext\n"
                        "from awsglue.job import Job\n"
                        "from pyspark.sql import SparkSession\n"
                        "\n"
                        "args = getResolvedOptions(sys.argv, ['JOB_NAME'])\n"
                        "sc = SparkContext()\n"
                        "glueContext = GlueContext(sc)\n"
                        "spark = glueContext.spark_session\n"
                        "job = Job(glueContext)\n"
                        "job.init(args['JOB_NAME'], args)\n"
                        "\n"
                        'print("=== Glue 5.0 Job Started ===")\n'
                        'print(f"Python version: {sys.version}")\n'
                        'print(f"Spark version: {spark.version}")\n'
                        'print(f"Job name: {args[\'JOB_NAME\']}")\n'
                        "\n"
                        'data = [("test", 1, "success"), ("glue", 2, "running"), ("job", 3, "complete")]\n'
                        'columns = ["name", "id", "status"]\n'
                        "df = spark.createDataFrame(data, columns)\n"
                        'print("Created test DataFrame:")\n'
                        "df.show()\n"
                        "\n"
                        'print("=== Glue 5.0 Job Completed Successfully ===")\n'
                        "job.commit()\n"
                    ),
                    "replace": True,
                    "s3_bucket": "{{ ti.xcom_pull(task_ids='create_glue_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                    "s3_key": "{{ params.script_key }}",
                    "task_id": "create_script",
                    "dependencies": ["wait_for_glue_stack"],
                },
                "run_glue_job": {
                    "operator": "GlueJobOperator",
                    "concurrent_run_limit": 1,
                    "create_job_kwargs": {
                        "GlueVersion": "5.0",
                        "Command": {
                            "Name": "glueetl",
                            "ScriptLocation": "s3://{{ ti.xcom_pull(task_ids='create_glue_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}/{{ params.script_key }}",
                            "PythonVersion": "3",
                        },
                        "DefaultArguments": {
                            "--job-language": "python",
                            "--enable-metrics": "",
                            "--enable-continuous-cloudwatch-log": "true",
                        },
                        "MaxRetries": 0,
                        "Timeout": 60,
                    },
                    "iam_role_name": "{{ ti.xcom_pull(task_ids='create_glue_stack')['CreateStackResponse']['Outputs'][1]['OutputValue'] }}",
                    "job_desc": "AWS Glue Job with Airflow",
                    "job_name": "glue5-python3-job-{{ ds_nodash }}",
                    "task_id": "run_glue_job",
                    "wait_for_completion": True,
                    "dependencies": ["create_script"],
                },
                "delete_glue_stack": {
                    "operator": "CloudFormationDeleteStackOperator",
                    "stack_name": "{{ params.stack_name }}",
                    "task_id": "delete_glue_stack",
                    "trigger_rule": "all_done",
                    "dependencies": ["run_glue_job"],
                },
                "wait_for_glue_delete": {
                    "operator": "CloudFormationDeleteStackSensor",
                    "stack_name": "{{ params.stack_name }}",
                    "task_id": "wait_for_glue_delete",
                    "dependencies": ["delete_glue_stack"],
                },
            },
        },
        "athena": {
            "default_params": {"output_location": "s3://amzn-s3-demo-bucket/athena-results/"},
            "extra_fields": {"dag_id": "athena_dag"},
            "tasks": {
                "create_stack": {
                    "operator": "CloudFormationCreateStackOperator",
                    "cloudformation_parameters": {
                        "StackName": "covid-lake-stack",
                        "TemplateURL": "https://covid19-lake.s3.us-east-2.amazonaws.com/cfn/CovidLakeStack.template.json",
                        "TimeoutInMinutes": 5,
                        "OnFailure": "DELETE",
                    },
                    "stack_name": "covid-lake-stack",
                    "task_id": "create_stack",
                    "dependencies": [],
                },
                "wait_for_stack_create": {
                    "operator": "CloudFormationCreateStackSensor",
                    "stack_name": "covid-lake-stack",
                    "task_id": "wait_for_stack_create",
                    "dependencies": ["create_stack"],
                },
                "query_1": {
                    "operator": "AthenaOperator",
                    "database": "default",
                    "output_location": "{{ params.output_location }}",
                    "query": (
                        'SELECT cases.fips, admin2 as county, province_state, confirmed, growth_count,\n'
                        '  sum(num_licensed_beds) as num_licensed_beds,\n'
                        '  sum(num_staffed_beds) as num_staffed_beds,\n'
                        '  sum(num_icu_beds) as num_icu_beds\n'
                        'FROM "covid-19"."hospital_beds" beds,\n'
                        '  (SELECT fips, admin2, province_state, confirmed,\n'
                        '    last_value(confirmed) over (partition by fips order by last_update) -\n'
                        '    first_value(confirmed) over (partition by fips order by last_update) as growth_count,\n'
                        '    first_value(last_update) over (partition by fips order by last_update desc) as most_recent,\n'
                        '    last_update\n'
                        '  FROM "covid-19"."enigma_jhu"\n'
                        "  WHERE from_iso8601_timestamp(last_update) > now() - interval '200' day\n"
                        "    AND country_region = 'US') cases\n"
                        'WHERE beds.fips = cases.fips AND last_update = most_recent\n'
                        'GROUP BY cases.fips, confirmed, growth_count, admin2, province_state\n'
                        'ORDER BY growth_count desc\n'
                    ),
                    "task_id": "query_1",
                    "dependencies": ["wait_for_stack_create"],
                },
                "query_2": {
                    "operator": "AthenaOperator",
                    "database": "default",
                    "output_location": "{{ params.output_location }}",
                    "query": 'SELECT * FROM "covid-19"."world_cases_deaths_testing" order by "date" desc limit 10;\n',
                    "task_id": "query_2",
                    "dependencies": ["wait_for_stack_create"],
                },
                "query_3": {
                    "operator": "AthenaOperator",
                    "database": "default",
                    "output_location": "{{ params.output_location }}",
                    "query": (
                        'SELECT date, positive, negative, pending, hospitalized, death, total,\n'
                        '  deathincrease, hospitalizedincrease, negativeincrease, positiveincrease,\n'
                        '  sta.state AS state_abbreviation, abb.state\n'
                        'FROM "covid-19"."covid_testing_states_daily" sta\n'
                        'JOIN "covid-19"."us_state_abbreviations" abb ON sta.state = abb.abbreviation\n'
                        'limit 500;\n'
                    ),
                    "task_id": "query_3",
                    "dependencies": ["wait_for_stack_create"],
                },
                "delete_stack": {
                    "operator": "CloudFormationDeleteStackOperator",
                    "stack_name": "covid-lake-stack",
                    "task_id": "delete_stack",
                    "trigger_rule": "all_done",
                    "dependencies": ["query_1", "query_3", "query_2"],
                },
                "wait_for_stack_delete": {
                    "operator": "CloudFormationDeleteStackSensor",
                    "stack_name": "covid-lake-stack",
                    "task_id": "wait_for_stack_delete",
                    "trigger_rule": "all_success",
                    "dependencies": ["delete_stack"],
                },
            },
        },
        "bedrock": {
            "default_params": {"model_id": "amazon.nova-lite-v1:0"},
            "tasks": [
                {
                    "task_id": "invoke_model",
                    "operator": "BedrockInvokeModelOperator",
                    "parameters": {
                        "model_id": "{{ params.model_id }}",
                        "input_data": {
                            "messages": [{"role": "user", "content": [{"text": "What is Amazon MWAA?"}]}],
                        },
                    },
                },
            ],
        },
        "lambda": {
            "default_params": {"function_name": "mwaa-test-lambda", "stack_name": "mwaa-test-lambda-stack"},
            "tasks": [
                {
                    "task_id": "create_lambda_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  LambdaRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: lambda.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole\n"
                                "  TestFunction:\n"
                                "    Type: AWS::Lambda::Function\n"
                                "    Properties:\n"
                                "      FunctionName: !Ref FunctionName\n"
                                "      Runtime: python3.12\n"
                                "      Handler: index.handler\n"
                                "      Role: !GetAtt LambdaRole.Arn\n"
                                "      Code:\n"
                                "        ZipFile: |\n"
                                "          def handler(event, context):\n"
                                "              return {'statusCode': 200, 'body': 'Hello from MWAA Serverless test'}\n"
                                "Parameters:\n"
                                "  FunctionName:\n"
                                "    Type: String\n"
                                "    Default: mwaa-test-lambda\n"
                                "Outputs:\n"
                                "  FunctionName:\n"
                                "    Value: !Ref TestFunction\n"
                            ),
                            "Parameters": [{"ParameterKey": "FunctionName", "ParameterValue": "{{ params.function_name }}"}],
                        },
                    },
                },
                {
                    "task_id": "wait_for_lambda_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_lambda_stack"],
                },
                {
                    "task_id": "invoke_function",
                    "operator": "LambdaInvokeFunctionOperator",
                    "parameters": {
                        "function_name": "{{ params.function_name }}",
                        "payload": '{"action": "test"}',
                    },
                    "upstream_tasks": ["wait_for_lambda_stack"],
                },
                {
                    "task_id": "delete_lambda_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["invoke_function"],
                },
                {
                    "task_id": "wait_for_lambda_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_lambda_stack"],
                },
            ],
        },
        "emr_serverless": {
            "default_params": {"application_name": "mwaa-test-emr-app", "stack_name": "mwaa-test-emr-serverless-stack"},
            "tasks": [
                {
                    "task_id": "create_emr_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  EmrServerlessRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: emr-serverless.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess\n"
                                "  ScriptBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "Outputs:\n"
                                "  RoleArn:\n"
                                "    Value: !GetAtt EmrServerlessRole.Arn\n"
                                "  ScriptBucketName:\n"
                                "    Value: !Ref ScriptBucket\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_emr_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_emr_stack"],
                },
                {
                    "task_id": "create_application",
                    "operator": "EmrServerlessCreateApplicationOperator",
                    "parameters": {
                        "release_label": "emr-7.0.0",
                        "job_type": "SPARK",
                        "client_request_token": "{{ ds_nodash }}",
                    },
                    "upstream_tasks": ["wait_for_emr_stack"],
                },
                {
                    "task_id": "stop_application",
                    "operator": "EmrServerlessStopApplicationOperator",
                    "parameters": {
                        "application_id": "{{ ti.xcom_pull(task_ids='create_application') }}",
                    },
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["create_application"],
                },
                {
                    "task_id": "delete_application",
                    "operator": "EmrServerlessDeleteApplicationOperator",
                    "parameters": {
                        "application_id": "{{ ti.xcom_pull(task_ids='create_application') }}",
                    },
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["stop_application"],
                },
                {
                    "task_id": "delete_emr_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["delete_application"],
                },
                {
                    "task_id": "wait_for_emr_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_emr_stack"],
                },
            ],
        },
        "batch": {
            "default_params": {"stack_name": "mwaa-test-batch-stack"},
            "tasks": [
                {
                    "task_id": "create_batch_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  BatchServiceRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: batch.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole\n"
                                "  ComputeEnv:\n"
                                "    Type: AWS::Batch::ComputeEnvironment\n"
                                "    Properties:\n"
                                "      Type: MANAGED\n"
                                "      ComputeResources:\n"
                                "        Type: FARGATE\n"
                                "        MaxvCpus: 4\n"
                                "        Subnets:\n"
                                "          - !Ref PublicSubnet\n"
                                "        SecurityGroupIds:\n"
                                "          - !GetAtt VPC.DefaultSecurityGroup\n"
                                "      ServiceRole: !GetAtt BatchServiceRole.Arn\n"
                                "  VPC:\n"
                                "    Type: AWS::EC2::VPC\n"
                                "    Properties:\n"
                                "      CidrBlock: 10.0.0.0/16\n"
                                "      EnableDnsSupport: true\n"
                                "      EnableDnsHostnames: true\n"
                                "  PublicSubnet:\n"
                                "    Type: AWS::EC2::Subnet\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      CidrBlock: 10.0.1.0/24\n"
                                "      MapPublicIpOnLaunch: true\n"
                                "  IGW:\n"
                                "    Type: AWS::EC2::InternetGateway\n"
                                "  AttachIGW:\n"
                                "    Type: AWS::EC2::VPCGatewayAttachment\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      InternetGatewayId: !Ref IGW\n"
                                "  JobQueue:\n"
                                "    Type: AWS::Batch::JobQueue\n"
                                "    Properties:\n"
                                "      Priority: 1\n"
                                "      ComputeEnvironmentOrder:\n"
                                "        - Order: 1\n"
                                "          ComputeEnvironment: !Ref ComputeEnv\n"
                                "  JobDef:\n"
                                "    Type: AWS::Batch::JobDefinition\n"
                                "    Properties:\n"
                                "      Type: container\n"
                                "      PlatformCapabilities:\n"
                                "        - FARGATE\n"
                                "      ContainerProperties:\n"
                                "        Image: public.ecr.aws/amazonlinux/amazonlinux:2023\n"
                                "        Command:\n"
                                "          - echo\n"
                                "          - Hello from MWAA Serverless Batch test\n"
                                "        ResourceRequirements:\n"
                                "          - Type: VCPU\n"
                                "            Value: '0.25'\n"
                                "          - Type: MEMORY\n"
                                "            Value: '512'\n"
                                "        ExecutionRoleArn: !GetAtt EcsTaskRole.Arn\n"
                                "  EcsTaskRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: ecs-tasks.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy\n"
                                "Outputs:\n"
                                "  JobQueueArn:\n"
                                "    Value: !Ref JobQueue\n"
                                "  JobDefArn:\n"
                                "    Value: !Ref JobDef\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_batch_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_batch_stack"],
                },
                {
                    "task_id": "submit_job",
                    "operator": "BatchOperator",
                    "parameters": {
                        "job_name": "batch-job-{{ ds_nodash }}",
                        "job_definition": "{{ ti.xcom_pull(task_ids='create_batch_stack')['CreateStackResponse']['Outputs'][1]['OutputValue'] }}",
                        "job_queue": "{{ ti.xcom_pull(task_ids='create_batch_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "wait_for_completion": True,
                    },
                    "upstream_tasks": ["wait_for_batch_stack"],
                },
                {
                    "task_id": "delete_batch_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["submit_job"],
                },
                {
                    "task_id": "wait_for_batch_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_batch_stack"],
                },
            ],
        },
        "step_functions": {
            "default_params": {"state_machine_name": "mwaa-test-sfn", "stack_name": "mwaa-test-sfn-stack"},
            "tasks": [
                {
                    "task_id": "create_sfn_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Parameters:\n"
                                "  StateMachineName:\n"
                                "    Type: String\n"
                                "    Default: mwaa-test-sfn\n"
                                "Resources:\n"
                                "  SfnRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: states.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "  TestStateMachine:\n"
                                "    Type: AWS::StepFunctions::StateMachine\n"
                                "    Properties:\n"
                                "      StateMachineName: !Ref StateMachineName\n"
                                "      RoleArn: !GetAtt SfnRole.Arn\n"
                                "      DefinitionString: |\n"
                                "        {\"Comment\": \"Test\", \"StartAt\": \"Pass\", \"States\": {\"Pass\": {\"Type\": \"Pass\", \"Result\": \"Hello from MWAA\", \"End\": true}}}\n"
                                "Outputs:\n"
                                "  StateMachineArn:\n"
                                "    Value: !Ref TestStateMachine\n"
                            ),
                            "Parameters": [{"ParameterKey": "StateMachineName", "ParameterValue": "{{ params.state_machine_name }}"}],
                        },
                    },
                },
                {
                    "task_id": "wait_for_sfn_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_sfn_stack"],
                },
                {
                    "task_id": "start_execution",
                    "operator": "StepFunctionStartExecutionOperator",
                    "parameters": {
                        "state_machine_arn": "{{ ti.xcom_pull(task_ids='create_sfn_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "state_machine_input": '{"key": "value"}',
                    },
                    "upstream_tasks": ["wait_for_sfn_stack"],
                },
                {
                    "task_id": "wait_for_execution",
                    "operator": "StepFunctionExecutionSensor",
                    "parameters": {
                        "execution_arn": "{{ ti.xcom_pull(task_ids='start_execution') }}",
                    },
                    "upstream_tasks": ["start_execution"],
                },
                {
                    "task_id": "delete_sfn_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_execution"],
                },
                {
                    "task_id": "wait_for_sfn_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_sfn_stack"],
                },
            ],
        },
        "redshift": {
            "default_params": {"database": "dev", "stack_name": "mwaa-test-redshift-stack"},
            "tasks": [
                {
                    "task_id": "create_redshift_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  RedshiftNamespace:\n"
                                "    Type: AWS::RedshiftServerless::Namespace\n"
                                "    Properties:\n"
                                "      NamespaceName: mwaa-test-ns\n"
                                "      DbName: dev\n"
                                "      AdminUsername: admin\n"
                                "      AdminUserPassword: REPLACE_ME_SecurePassword1!\n"
                                "  RedshiftWorkgroup:\n"
                                "    Type: AWS::RedshiftServerless::Workgroup\n"
                                "    Properties:\n"
                                "      WorkgroupName: mwaa-test-wg\n"
                                "      NamespaceName: !Ref RedshiftNamespace\n"
                                "      BaseCapacity: 8\n"
                                "      PubliclyAccessible: false\n"
                                "Outputs:\n"
                                "  WorkgroupName:\n"
                                "    Value: mwaa-test-wg\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_redshift_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_redshift_stack"],
                },
                {
                    "task_id": "run_query",
                    "operator": "RedshiftDataOperator",
                    "parameters": {
                        "sql": "SELECT 1;",
                        "database": "{{ params.database }}",
                        "workgroup_name": "mwaa-test-wg",
                        "wait_for_completion": True,
                    },
                    "upstream_tasks": ["wait_for_redshift_stack"],
                },
                {
                    "task_id": "delete_redshift_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["run_query"],
                },
                {
                    "task_id": "wait_for_redshift_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_redshift_stack"],
                },
            ],
        },
        "sns": {
            "default_params": {"topic_name": "mwaa-test-sns-topic", "stack_name": "mwaa-test-sns-stack"},
            "tasks": [
                {
                    "task_id": "create_sns_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Parameters:\n"
                                "  TopicName:\n"
                                "    Type: String\n"
                                "    Default: mwaa-test-sns-topic\n"
                                "Resources:\n"
                                "  TestTopic:\n"
                                "    Type: AWS::SNS::Topic\n"
                                "    Properties:\n"
                                "      TopicName: !Ref TopicName\n"
                                "Outputs:\n"
                                "  TopicArn:\n"
                                "    Value: !Ref TestTopic\n"
                            ),
                            "Parameters": [{"ParameterKey": "TopicName", "ParameterValue": "{{ params.topic_name }}"}],
                        },
                    },
                },
                {
                    "task_id": "wait_for_sns_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_sns_stack"],
                },
                {
                    "task_id": "publish_message",
                    "operator": "SnsPublishOperator",
                    "parameters": {
                        "target_arn": "{{ ti.xcom_pull(task_ids='create_sns_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "message": "Hello from MWAA Serverless test",
                    },
                    "upstream_tasks": ["wait_for_sns_stack"],
                },
                {
                    "task_id": "delete_sns_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["publish_message"],
                },
                {
                    "task_id": "wait_for_sns_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_sns_stack"],
                },
            ],
        },
        "ecs": {
            "default_params": {"stack_name": "mwaa-test-ecs-stack"},
            "tasks": [
                {
                    "task_id": "create_ecs_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  VPC:\n"
                                "    Type: AWS::EC2::VPC\n"
                                "    Properties:\n"
                                "      CidrBlock: 10.0.0.0/16\n"
                                "      EnableDnsSupport: true\n"
                                "      EnableDnsHostnames: true\n"
                                "  PublicSubnet:\n"
                                "    Type: AWS::EC2::Subnet\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      CidrBlock: 10.0.1.0/24\n"
                                "      MapPublicIpOnLaunch: true\n"
                                "  IGW:\n"
                                "    Type: AWS::EC2::InternetGateway\n"
                                "  AttachIGW:\n"
                                "    Type: AWS::EC2::VPCGatewayAttachment\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      InternetGatewayId: !Ref IGW\n"
                                "  EcsCluster:\n"
                                "    Type: AWS::ECS::Cluster\n"
                                "    Properties:\n"
                                "      ClusterName: mwaa-test-ecs-cluster\n"
                                "  TaskRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: ecs-tasks.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy\n"
                                "  TaskDef:\n"
                                "    Type: AWS::ECS::TaskDefinition\n"
                                "    Properties:\n"
                                "      Family: mwaa-test-task\n"
                                "      Cpu: '256'\n"
                                "      Memory: '512'\n"
                                "      NetworkMode: awsvpc\n"
                                "      RequiresCompatibilities:\n"
                                "        - FARGATE\n"
                                "      ExecutionRoleArn: !GetAtt TaskRole.Arn\n"
                                "      ContainerDefinitions:\n"
                                "        - Name: test-container\n"
                                "          Image: public.ecr.aws/amazonlinux/amazonlinux:2023\n"
                                "          Command:\n"
                                "            - echo\n"
                                "            - Hello from MWAA Serverless ECS test\n"
                                "          Essential: true\n"
                                "Outputs:\n"
                                "  ClusterName:\n"
                                "    Value: !Ref EcsCluster\n"
                                "  TaskDefArn:\n"
                                "    Value: !Ref TaskDef\n"
                                "  SubnetId:\n"
                                "    Value: !Ref PublicSubnet\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_ecs_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_ecs_stack"],
                },
                {
                    "task_id": "run_task",
                    "operator": "EcsRunTaskOperator",
                    "parameters": {
                        "cluster": "mwaa-test-ecs-cluster",
                        "task_definition": "mwaa-test-task",
                        "launch_type": "FARGATE",
                        "overrides": {},
                        "network_configuration": {
                            "awsvpcConfiguration": {
                                "subnets": ["{{ ti.xcom_pull(task_ids='create_ecs_stack')['CreateStackResponse']['Outputs'][2]['OutputValue'] }}"],
                                "assignPublicIp": "ENABLED",
                            },
                        },
                    },
                    "upstream_tasks": ["wait_for_ecs_stack"],
                },
                {
                    "task_id": "delete_ecs_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["run_task"],
                },
                {
                    "task_id": "wait_for_ecs_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_ecs_stack"],
                },
            ],
        },
        "eks": {
            "default_params": {"cluster_name": "mwaa-test-eks", "stack_name": "mwaa-test-eks-stack"},
            "tasks": [
                {
                    "task_id": "create_eks_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  VPC:\n"
                                "    Type: AWS::EC2::VPC\n"
                                "    Properties:\n"
                                "      CidrBlock: 10.0.0.0/16\n"
                                "      EnableDnsSupport: true\n"
                                "      EnableDnsHostnames: true\n"
                                "  SubnetA:\n"
                                "    Type: AWS::EC2::Subnet\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      CidrBlock: 10.0.1.0/24\n"
                                "      AvailabilityZone: !Select [0, !GetAZs '']\n"
                                "  SubnetB:\n"
                                "    Type: AWS::EC2::Subnet\n"
                                "    Properties:\n"
                                "      VpcId: !Ref VPC\n"
                                "      CidrBlock: 10.0.2.0/24\n"
                                "      AvailabilityZone: !Select [1, !GetAZs '']\n"
                                "  EksRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: eks.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/AmazonEKSClusterPolicy\n"
                                "Outputs:\n"
                                "  RoleArn:\n"
                                "    Value: !GetAtt EksRole.Arn\n"
                                "  SubnetAId:\n"
                                "    Value: !Ref SubnetA\n"
                                "  SubnetBId:\n"
                                "    Value: !Ref SubnetB\n"
                                "  SecurityGroupId:\n"
                                "    Value: !GetAtt VPC.DefaultSecurityGroup\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_eks_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_eks_stack"],
                },
                {
                    "task_id": "create_cluster",
                    "operator": "EksCreateClusterOperator",
                    "parameters": {
                        "cluster_name": "{{ params.cluster_name }}",
                        "cluster_role_arn": "{{ ti.xcom_pull(task_ids='create_eks_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "resources_vpc_config": {
                            "subnetIds": [
                                "{{ ti.xcom_pull(task_ids='create_eks_stack')['CreateStackResponse']['Outputs'][1]['OutputValue'] }}",
                                "{{ ti.xcom_pull(task_ids='create_eks_stack')['CreateStackResponse']['Outputs'][2]['OutputValue'] }}",
                            ],
                            "securityGroupIds": [
                                "{{ ti.xcom_pull(task_ids='create_eks_stack')['CreateStackResponse']['Outputs'][3]['OutputValue'] }}",
                            ],
                        },
                    },
                    "upstream_tasks": ["wait_for_eks_stack"],
                },
                {
                    "task_id": "wait_for_cluster",
                    "operator": "EksClusterStateSensor",
                    "parameters": {"cluster_name": "{{ params.cluster_name }}", "target_state": "ACTIVE"},
                    "upstream_tasks": ["create_cluster"],
                },
                {
                    "task_id": "delete_cluster",
                    "operator": "EksDeleteClusterOperator",
                    "parameters": {"cluster_name": "{{ params.cluster_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_cluster"],
                },
                {
                    "task_id": "delete_eks_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["delete_cluster"],
                },
                {
                    "task_id": "wait_for_eks_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_eks_stack"],
                },
            ],
        },
        "emr": {
            "default_params": {"log_uri": "s3://amzn-s3-demo-bucket/emr-logs/", "stack_name": "mwaa-test-emr-stack"},
            "tasks": [
                {
                    "task_id": "create_emr_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  LogBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  EmrServiceRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: elasticmapreduce.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AmazonEMRServicePolicy_v2\n"
                                "  EmrEc2Role:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: ec2.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AmazonElasticMapReduceforEC2Role\n"
                                "  EmrInstanceProfile:\n"
                                "    Type: AWS::IAM::InstanceProfile\n"
                                "    Properties:\n"
                                "      Roles:\n"
                                "        - !Ref EmrEc2Role\n"
                                "Outputs:\n"
                                "  LogBucketUri:\n"
                                "    Value: !Sub 's3://${LogBucket}/emr-logs/'\n"
                                "  ServiceRoleName:\n"
                                "    Value: !Ref EmrServiceRole\n"
                                "  InstanceProfileName:\n"
                                "    Value: !Ref EmrInstanceProfile\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_emr_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_emr_stack"],
                },
                {
                    "task_id": "create_job_flow",
                    "operator": "EmrCreateJobFlowOperator",
                    "parameters": {
                        "emr_conn_id": "aws_default",
                        "job_flow_overrides": {
                            "Name": "emr-cluster-{{ ds_nodash }}",
                            "LogUri": "{{ ti.xcom_pull(task_ids='create_emr_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                            "ReleaseLabel": "emr-7.0.0",
                            "ServiceRole": "{{ ti.xcom_pull(task_ids='create_emr_stack')['CreateStackResponse']['Outputs'][1]['OutputValue'] }}",
                            "JobFlowRole": "{{ ti.xcom_pull(task_ids='create_emr_stack')['CreateStackResponse']['Outputs'][2]['OutputValue'] }}",
                            "Instances": {"InstanceGroups": [{"Name": "Primary", "Market": "ON_DEMAND", "InstanceRole": "MASTER", "InstanceType": "m5.xlarge", "InstanceCount": 1}], "KeepJobFlowAliveWhenNoSteps": False, "TerminationProtected": False},
                        },
                    },
                    "upstream_tasks": ["wait_for_emr_stack"],
                },
                {
                    "task_id": "wait_for_job_flow",
                    "operator": "EmrJobFlowSensor",
                    "parameters": {"job_flow_id": "{{ ti.xcom_pull(task_ids='create_job_flow') }}", "target_states": ["TERMINATED"]},
                    "upstream_tasks": ["create_job_flow"],
                },
                {
                    "task_id": "delete_emr_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_job_flow"],
                },
                {
                    "task_id": "wait_for_emr_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_emr_stack"],
                },
            ],
        },
        "cloudformation": {
            "default_params": {"stack_name": "my-cfn-stack"},
            "tasks": [
                {
                    "task_id": "create_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}", "cloudformation_parameters": {"StackName": "{{ params.stack_name }}", "TemplateBody": "AWSTemplateFormatVersion: '2010-09-09'\nDescription: Sample stack\nResources:\n  Placeholder:\n    Type: AWS::CloudFormation::WaitConditionHandle\n"}},
                },
                {
                    "task_id": "wait_for_create",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_stack"],
                },
                {
                    "task_id": "delete_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_create"],
                },
                {
                    "task_id": "wait_for_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_stack"],
                },
            ],
        },
        "sagemaker": {
            "default_params": {"instance_type": "ml.m5.large", "stack_name": "mwaa-test-sagemaker-stack", "image_uri": "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"},
            "tasks": [
                {
                    "task_id": "create_sagemaker_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  SageMakerRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: sagemaker.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/AmazonSageMakerFullAccess\n"
                                "Outputs:\n"
                                "  RoleArn:\n"
                                "    Value: !GetAtt SageMakerRole.Arn\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_sagemaker_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_sagemaker_stack"],
                },
                {
                    "task_id": "start_processing",
                    "operator": "SageMakerProcessingOperator",
                    "parameters": {
                        "config": {
                            "ProcessingJobName": "processing-job-{{ ds_nodash }}",
                            "RoleArn": "{{ ti.xcom_pull(task_ids='create_sagemaker_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                            "ProcessingResources": {"ClusterConfig": {"InstanceCount": 1, "InstanceType": "{{ params.instance_type }}", "VolumeSizeInGB": 10}},
                            "AppSpecification": {"ImageUri": "{{ params.image_uri }}"},
                        },
                        "wait_for_completion": True,
                    },
                    "upstream_tasks": ["wait_for_sagemaker_stack"],
                },
                {
                    "task_id": "delete_sagemaker_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["start_processing"],
                },
                {
                    "task_id": "wait_for_sagemaker_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_sagemaker_stack"],
                },
            ],
        },
        "rds": {
            "default_params": {"stack_name": "mwaa-test-rds-stack"},
            "tasks": [
                {
                    "task_id": "create_rds_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  TestDB:\n"
                                "    Type: AWS::RDS::DBInstance\n"
                                "    Properties:\n"
                                "      DBInstanceIdentifier: mwaa-test-db\n"
                                "      DBInstanceClass: db.t3.micro\n"
                                "      Engine: mysql\n"
                                "      MasterUsername: admin\n"
                                "      MasterUserPassword: REPLACE_ME_SecurePassword1!\n"
                                "      AllocatedStorage: '20'\n"
                                "      BackupRetentionPeriod: 0\n"
                                "      DeletionProtection: false\n"
                                "Outputs:\n"
                                "  DBInstanceId:\n"
                                "    Value: !Ref TestDB\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_rds_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_rds_stack"],
                },
                {
                    "task_id": "create_snapshot",
                    "operator": "RdsCreateDbSnapshotOperator",
                    "parameters": {"db_type": "instance", "db_identifier": "mwaa-test-db", "db_snapshot_identifier": "snapshot-{{ ds_nodash }}"},
                    "upstream_tasks": ["wait_for_rds_stack"],
                },
                {
                    "task_id": "wait_for_snapshot",
                    "operator": "RdsSnapshotExistenceSensor",
                    "parameters": {"db_type": "instance", "db_snapshot_identifier": "snapshot-{{ ds_nodash }}"},
                    "upstream_tasks": ["create_snapshot"],
                },
                {
                    "task_id": "delete_snapshot",
                    "operator": "RdsDeleteDbSnapshotOperator",
                    "parameters": {"db_type": "instance", "db_snapshot_identifier": "snapshot-{{ ds_nodash }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_snapshot"],
                },
                {
                    "task_id": "delete_rds_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["delete_snapshot"],
                },
                {
                    "task_id": "wait_for_rds_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_rds_stack"],
                },
            ],
        },
        "ec2": {
            "default_params": {"stack_name": "mwaa-test-ec2-stack"},
            "tasks": [
                {
                    "task_id": "create_ec2_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  TestInstance:\n"
                                "    Type: AWS::EC2::Instance\n"
                                "    Properties:\n"
                                "      InstanceType: t3.micro\n"
                                "      ImageId: resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64\n"
                                "Outputs:\n"
                                "  InstanceId:\n"
                                "    Value: !Ref TestInstance\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_ec2_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_ec2_stack"],
                },
                {
                    "task_id": "stop_instance",
                    "operator": "EC2StopInstanceOperator",
                    "parameters": {"instance_id": "{{ ti.xcom_pull(task_ids='create_ec2_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}"},
                    "upstream_tasks": ["wait_for_ec2_stack"],
                },
                {
                    "task_id": "wait_for_stopped",
                    "operator": "EC2InstanceStateSensor",
                    "parameters": {"instance_id": "{{ ti.xcom_pull(task_ids='create_ec2_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}", "target_state": "stopped"},
                    "upstream_tasks": ["stop_instance"],
                },
                {
                    "task_id": "start_instance",
                    "operator": "EC2StartInstanceOperator",
                    "parameters": {"instance_id": "{{ ti.xcom_pull(task_ids='create_ec2_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}"},
                    "upstream_tasks": ["wait_for_stopped"],
                },
                {
                    "task_id": "wait_for_running",
                    "operator": "EC2InstanceStateSensor",
                    "parameters": {"instance_id": "{{ ti.xcom_pull(task_ids='create_ec2_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}", "target_state": "running"},
                    "upstream_tasks": ["start_instance"],
                },
                {
                    "task_id": "delete_ec2_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_running"],
                },
                {
                    "task_id": "wait_for_ec2_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_ec2_stack"],
                },
            ],
        },
        "sqs": {
            "default_params": {"queue_name": "mwaa-test-sqs-queue", "stack_name": "mwaa-test-sqs-stack"},
            "tasks": [
                {
                    "task_id": "create_sqs_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Parameters:\n"
                                "  QueueName:\n"
                                "    Type: String\n"
                                "    Default: mwaa-test-sqs-queue\n"
                                "Resources:\n"
                                "  TestQueue:\n"
                                "    Type: AWS::SQS::Queue\n"
                                "    Properties:\n"
                                "      QueueName: !Ref QueueName\n"
                                "Outputs:\n"
                                "  QueueUrl:\n"
                                "    Value: !Ref TestQueue\n"
                            ),
                            "Parameters": [{"ParameterKey": "QueueName", "ParameterValue": "{{ params.queue_name }}"}],
                        },
                    },
                },
                {
                    "task_id": "wait_for_sqs_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_sqs_stack"],
                },
                {
                    "task_id": "publish_message",
                    "operator": "SqsPublishOperator",
                    "parameters": {
                        "sqs_queue": "{{ ti.xcom_pull(task_ids='create_sqs_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "message_content": '{"event": "workflow_started"}',
                    },
                    "upstream_tasks": ["wait_for_sqs_stack"],
                },
                {
                    "task_id": "wait_for_message",
                    "operator": "SqsSensor",
                    "parameters": {
                        "sqs_queue": "{{ ti.xcom_pull(task_ids='create_sqs_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                    },
                    "upstream_tasks": ["publish_message"],
                },
                {
                    "task_id": "delete_sqs_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_message"],
                },
                {
                    "task_id": "wait_for_sqs_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_sqs_stack"],
                },
            ],
        },
        "eventbridge": {
            "default_params": {"stack_name": "mwaa-test-eb-stack"},
            "tasks": [
                {
                    "task_id": "create_eb_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  TestEventBus:\n"
                                "    Type: AWS::Events::EventBus\n"
                                "    Properties:\n"
                                "      Name: mwaa-test-event-bus\n"
                                "  TestRule:\n"
                                "    Type: AWS::Events::Rule\n"
                                "    Properties:\n"
                                "      Name: mwaa-test-eb-rule\n"
                                "      EventBusName: !Ref TestEventBus\n"
                                "      EventPattern:\n"
                                "        source:\n"
                                "          - mwaa.serverless\n"
                                "      State: ENABLED\n"
                                "Outputs:\n"
                                "  EventBusName:\n"
                                "    Value: !Ref TestEventBus\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_eb_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_eb_stack"],
                },
                {
                    "task_id": "put_events",
                    "operator": "EventBridgePutEventsOperator",
                    "parameters": {
                        "entries": [{"Source": "mwaa.serverless", "DetailType": "WorkflowEvent", "Detail": '{"status": "started"}', "EventBusName": "mwaa-test-event-bus"}],
                    },
                    "upstream_tasks": ["wait_for_eb_stack"],
                },
                {
                    "task_id": "disable_rule",
                    "operator": "EventBridgeDisableRuleOperator",
                    "parameters": {
                        "name": "mwaa-test-eb-rule",
                        "event_bus_name": "mwaa-test-event-bus",
                    },
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["put_events"],
                },
                {
                    "task_id": "delete_eb_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["disable_rule"],
                },
                {
                    "task_id": "wait_for_eb_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_eb_stack"],
                },
            ],
        },
        "comprehend": {
            "default_params": {"stack_name": "mwaa-test-comprehend-stack"},
            "tasks": [
                {
                    "task_id": "create_comprehend_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  DataBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  ComprehendRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: comprehend.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      Policies:\n"
                                "        - PolicyName: S3Access\n"
                                "          PolicyDocument:\n"
                                "            Version: '2012-10-17'\n"
                                "            Statement:\n"
                                "              - Effect: Allow\n"
                                "                Action: s3:*\n"
                                "                Resource:\n"
                                "                  - !GetAtt DataBucket.Arn\n"
                                "                  - !Sub '${DataBucket.Arn}/*'\n"
                                "Outputs:\n"
                                "  InputS3Uri:\n"
                                "    Value: !Sub 's3://${DataBucket}/input/'\n"
                                "  OutputS3Uri:\n"
                                "    Value: !Sub 's3://${DataBucket}/output/'\n"
                                "  BucketName:\n"
                                "    Value: !Ref DataBucket\n"
                                "  RoleArn:\n"
                                "    Value: !GetAtt ComprehendRole.Arn\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_comprehend_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_comprehend_stack"],
                },
                {
                    "task_id": "upload_test_data",
                    "operator": "S3CreateObjectOperator",
                    "parameters": {
                        "s3_bucket": "{{ ti.xcom_pull(task_ids='create_comprehend_stack')['CreateStackResponse']['Outputs'][2]['OutputValue'] }}",
                        "s3_key": "input/test.txt",
                        "data": "Jane Doe lives at 100 Main St and her email is jane.doe@example.com",
                        "replace": True,
                    },
                    "upstream_tasks": ["wait_for_comprehend_stack"],
                },
                {
                    "task_id": "start_pii_detection",
                    "operator": "ComprehendStartPiiEntitiesDetectionJobOperator",
                    "parameters": {
                        "input_data_config": {
                            "S3Uri": "{{ ti.xcom_pull(task_ids='create_comprehend_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                            "InputFormat": "ONE_DOC_PER_LINE",
                        },
                        "output_data_config": {
                            "S3Uri": "{{ ti.xcom_pull(task_ids='create_comprehend_stack')['CreateStackResponse']['Outputs'][1]['OutputValue'] }}",
                        },
                        "mode": "ONLY_REDACTION",
                        "data_access_role_arn": "{{ ti.xcom_pull(task_ids='create_comprehend_stack')['CreateStackResponse']['Outputs'][3]['OutputValue'] }}",
                        "language_code": "en",
                    },
                    "upstream_tasks": ["upload_test_data"],
                },
                {
                    "task_id": "wait_for_pii_detection",
                    "operator": "ComprehendStartPiiEntitiesDetectionJobCompletedSensor",
                    "parameters": {"job_id": "{{ ti.xcom_pull(task_ids='start_pii_detection') }}"},
                    "upstream_tasks": ["start_pii_detection"],
                },
                {
                    "task_id": "delete_comprehend_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_pii_detection"],
                },
                {
                    "task_id": "wait_for_comprehend_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_comprehend_stack"],
                },
            ],
        },
        "dms": {
            "default_params": {"stack_name": "mwaa-test-dms-stack"},
            "tasks": [
                {
                    "task_id": "create_dms_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Description: DMS replication instance for testing\n"
                                "Resources:\n"
                                "  DmsRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      RoleName: dms-vpc-role\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: dms.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      ManagedPolicyArns:\n"
                                "        - arn:aws:iam::aws:policy/service-role/AmazonDMSVPCManagementRole\n"
                                "  ReplicationInstance:\n"
                                "    Type: AWS::DMS::ReplicationInstance\n"
                                "    DependsOn: DmsRole\n"
                                "    Properties:\n"
                                "      ReplicationInstanceClass: dms.t3.micro\n"
                                "      ReplicationInstanceIdentifier: mwaa-test-dms-ri\n"
                                "      PubliclyAccessible: false\n"
                                "Outputs:\n"
                                "  ReplicationInstanceArn:\n"
                                "    Value: !Ref ReplicationInstance\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_dms_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_dms_stack"],
                },
                {
                    "task_id": "delete_dms_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_dms_stack"],
                },
                {
                    "task_id": "wait_for_dms_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_dms_stack"],
                },
            ],
        },
        "kinesis_analytics": {
            "default_params": {"application_name": "mwaa-test-kinesis-app", "stack_name": "mwaa-test-kinesis-stack"},
            "tasks": [
                {
                    "task_id": "create_kinesis_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  KinesisRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: kinesisanalytics.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "Outputs:\n"
                                "  RoleArn:\n"
                                "    Value: !GetAtt KinesisRole.Arn\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_kinesis_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_kinesis_stack"],
                },
                {
                    "task_id": "create_application",
                    "operator": "KinesisAnalyticsV2CreateApplicationOperator",
                    "parameters": {
                        "application_name": "{{ params.application_name }}",
                        "runtime_environment": "FLINK-1_18",
                        "service_execution_role": "{{ ti.xcom_pull(task_ids='create_kinesis_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                    },
                    "upstream_tasks": ["wait_for_kinesis_stack"],
                },
                {
                    "task_id": "start_application",
                    "operator": "KinesisAnalyticsV2StartApplicationOperator",
                    "parameters": {"application_name": "{{ params.application_name }}"},
                    "upstream_tasks": ["create_application"],
                },
                {
                    "task_id": "stop_application",
                    "operator": "KinesisAnalyticsV2StopApplicationOperator",
                    "parameters": {"application_name": "{{ params.application_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["start_application"],
                },
                {
                    "task_id": "delete_kinesis_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["stop_application"],
                },
                {
                    "task_id": "wait_for_kinesis_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_kinesis_stack"],
                },
            ],
        },
        "neptune": {
            "default_params": {"stack_name": "mwaa-test-neptune-stack"},
            "tasks": [
                {
                    "task_id": "create_neptune_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  NeptuneCluster:\n"
                                "    Type: AWS::Neptune::DBCluster\n"
                                "    Properties:\n"
                                "      DBClusterIdentifier: mwaa-test-neptune\n"
                                "      EngineVersion: 1.4.7.0\n"
                                "      DeletionProtection: false\n"
                                "  NeptuneInstance:\n"
                                "    Type: AWS::Neptune::DBInstance\n"
                                "    Properties:\n"
                                "      DBClusterIdentifier: !Ref NeptuneCluster\n"
                                "      DBInstanceClass: db.t3.medium\n"
                                "Outputs:\n"
                                "  ClusterId:\n"
                                "    Value: !Ref NeptuneCluster\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_neptune_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_neptune_stack"],
                },
                {
                    "task_id": "stop_cluster",
                    "operator": "NeptuneStopDbClusterOperator",
                    "parameters": {"db_cluster_id": "mwaa-test-neptune"},
                    "upstream_tasks": ["wait_for_neptune_stack"],
                },
                {
                    "task_id": "start_cluster",
                    "operator": "NeptuneStartDbClusterOperator",
                    "parameters": {"db_cluster_id": "mwaa-test-neptune"},
                    "upstream_tasks": ["stop_cluster"],
                },
                {
                    "task_id": "delete_neptune_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["start_cluster"],
                },
                {
                    "task_id": "wait_for_neptune_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_neptune_stack"],
                },
            ],
        },
        "glacier": {
            "default_params": {"stack_name": "mwaa-test-glacier-stack"},
            "tasks": [
                {
                    "task_id": "create_glacier_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  TestVault:\n"
                                "    Type: AWS::Glacier::Vault\n"
                                "    Properties:\n"
                                "      VaultName: mwaa-test-vault\n"
                                "Outputs:\n"
                                "  VaultName:\n"
                                "    Value: !Ref TestVault\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_glacier_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_glacier_stack"],
                },
                {
                    "task_id": "create_inventory_job",
                    "operator": "GlacierCreateJobOperator",
                    "parameters": {"vault_name": "mwaa-test-vault"},
                    "upstream_tasks": ["wait_for_glacier_stack"],
                },
                {
                    "task_id": "wait_for_job",
                    "operator": "GlacierJobOperationSensor",
                    "parameters": {"vault_name": "mwaa-test-vault", "job_id": "{{ ti.xcom_pull(task_ids='create_inventory_job') }}"},
                    "upstream_tasks": ["create_inventory_job"],
                },
                {
                    "task_id": "delete_glacier_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_job"],
                },
                {
                    "task_id": "wait_for_glacier_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_glacier_stack"],
                },
            ],
        },
        "datasync": {
            "default_params": {"stack_name": "mwaa-test-datasync-stack"},
            "tasks": [
                {
                    "task_id": "create_datasync_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "Capabilities": ["CAPABILITY_IAM"],
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  SourceBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  DestBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  DataSyncRole:\n"
                                "    Type: AWS::IAM::Role\n"
                                "    Properties:\n"
                                "      AssumeRolePolicyDocument:\n"
                                "        Version: '2012-10-17'\n"
                                "        Statement:\n"
                                "          - Effect: Allow\n"
                                "            Principal:\n"
                                "              Service: datasync.amazonaws.com\n"
                                "            Action: sts:AssumeRole\n"
                                "      Policies:\n"
                                "        - PolicyName: S3Access\n"
                                "          PolicyDocument:\n"
                                "            Version: '2012-10-17'\n"
                                "            Statement:\n"
                                "              - Effect: Allow\n"
                                "                Action: s3:*\n"
                                "                Resource: '*'\n"
                                "  SourceLocation:\n"
                                "    Type: AWS::DataSync::LocationS3\n"
                                "    Properties:\n"
                                "      S3BucketArn: !GetAtt SourceBucket.Arn\n"
                                "      S3Config:\n"
                                "        BucketAccessRoleArn: !GetAtt DataSyncRole.Arn\n"
                                "  DestLocation:\n"
                                "    Type: AWS::DataSync::LocationS3\n"
                                "    Properties:\n"
                                "      S3BucketArn: !GetAtt DestBucket.Arn\n"
                                "      S3Config:\n"
                                "        BucketAccessRoleArn: !GetAtt DataSyncRole.Arn\n"
                                "  DataSyncTask:\n"
                                "    Type: AWS::DataSync::Task\n"
                                "    Properties:\n"
                                "      SourceLocationArn: !Ref SourceLocation\n"
                                "      DestinationLocationArn: !Ref DestLocation\n"
                                "Outputs:\n"
                                "  TaskArn:\n"
                                "    Value: !GetAtt DataSyncTask.TaskArn\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_datasync_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_datasync_stack"],
                },
                {
                    "task_id": "run_datasync",
                    "operator": "DataSyncOperator",
                    "parameters": {
                        "task_arn": "{{ ti.xcom_pull(task_ids='create_datasync_stack')['CreateStackResponse']['Outputs'][0]['OutputValue'] }}",
                        "wait_for_completion": True,
                    },
                    "upstream_tasks": ["wait_for_datasync_stack"],
                },
                {
                    "task_id": "delete_datasync_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["run_datasync"],
                },
                {
                    "task_id": "wait_for_datasync_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_datasync_stack"],
                },
            ],
        },
        "appflow": {
            "default_params": {"stack_name": "mwaa-test-appflow-stack"},
            "tasks": [
                {
                    "task_id": "create_appflow_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  SourceBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  DestBucket:\n"
                                "    Type: AWS::S3::Bucket\n"
                                "  TestFlow:\n"
                                "    Type: AWS::AppFlow::Flow\n"
                                "    Properties:\n"
                                "      FlowName: mwaa-test-flow\n"
                                "      TriggerConfig:\n"
                                "        TriggerType: OnDemand\n"
                                "      SourceFlowConfig:\n"
                                "        ConnectorType: S3\n"
                                "        SourceConnectorProperties:\n"
                                "          S3:\n"
                                "            BucketName: !Ref SourceBucket\n"
                                "            BucketPrefix: input\n"
                                "      DestinationFlowConfigList:\n"
                                "        - ConnectorType: S3\n"
                                "          DestinationConnectorProperties:\n"
                                "            S3:\n"
                                "              BucketName: !Ref DestBucket\n"
                                "              BucketPrefix: output\n"
                                "      Tasks:\n"
                                "        - TaskType: Map_all\n"
                                "          SourceFields: []\n"
                                "          TaskProperties:\n"
                                "            - Key: EXCLUDE_SOURCE_FIELDS_LIST\n"
                                "              Value: '[]'\n"
                                "Outputs:\n"
                                "  FlowName:\n"
                                "    Value: mwaa-test-flow\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_appflow_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_appflow_stack"],
                },
                {
                    "task_id": "run_flow",
                    "operator": "AppflowRunOperator",
                    "parameters": {"flow_name": "mwaa-test-flow", "wait_for_completion": True},
                    "upstream_tasks": ["wait_for_appflow_stack"],
                },
                {
                    "task_id": "delete_appflow_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["run_flow"],
                },
                {
                    "task_id": "wait_for_appflow_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_appflow_stack"],
                },
            ],
        },
        "quicksight": {
            "default_params": {"stack_name": "mwaa-test-quicksight-stack"},
            "tasks": [
                {
                    "task_id": "create_quicksight_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  DataSource:\n"
                                "    Type: AWS::QuickSight::DataSource\n"
                                "    Properties:\n"
                                "      AwsAccountId: !Ref AWS::AccountId\n"
                                "      DataSourceId: mwaa-test-datasource\n"
                                "      Name: mwaa-test-datasource\n"
                                "      Type: S3\n"
                                "  DataSet:\n"
                                "    Type: AWS::QuickSight::DataSet\n"
                                "    Properties:\n"
                                "      AwsAccountId: !Ref AWS::AccountId\n"
                                "      DataSetId: mwaa-test-dataset\n"
                                "      Name: mwaa-test-dataset\n"
                                "      ImportMode: SPICE\n"
                                "      PhysicalTableMap:\n"
                                "        PhysicalTable1:\n"
                                "          CustomSql:\n"
                                "            DataSourceArn: !GetAtt DataSource.Arn\n"
                                "            Name: test\n"
                                "            SqlQuery: SELECT 1 as id\n"
                                "            Columns:\n"
                                "              - Name: id\n"
                                "                Type: INTEGER\n"
                                "Outputs:\n"
                                "  DataSetId:\n"
                                "    Value: mwaa-test-dataset\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_quicksight_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_quicksight_stack"],
                },
                {
                    "task_id": "create_ingestion",
                    "operator": "QuickSightCreateIngestionOperator",
                    "parameters": {
                        "data_set_id": "mwaa-test-dataset",
                        "ingestion_id": "ingestion-{{ ds_nodash }}",
                    },
                    "upstream_tasks": ["wait_for_quicksight_stack"],
                },
                {
                    "task_id": "wait_for_ingestion",
                    "operator": "QuickSightSensor",
                    "parameters": {
                        "data_set_id": "mwaa-test-dataset",
                        "ingestion_id": "ingestion-{{ ds_nodash }}",
                    },
                    "upstream_tasks": ["create_ingestion"],
                },
                {
                    "task_id": "delete_quicksight_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_ingestion"],
                },
                {
                    "task_id": "wait_for_quicksight_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_quicksight_stack"],
                },
            ],
        },
        "dynamodb": {
            "default_params": {"stack_name": "mwaa-test-dynamodb-stack"},
            "tasks": [
                {
                    "task_id": "create_dynamodb_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  TestTable:\n"
                                "    Type: AWS::DynamoDB::Table\n"
                                "    Properties:\n"
                                "      TableName: mwaa-test-table\n"
                                "      BillingMode: PAY_PER_REQUEST\n"
                                "      AttributeDefinitions:\n"
                                "        - AttributeName: pk\n"
                                "          AttributeType: S\n"
                                "      KeySchema:\n"
                                "        - AttributeName: pk\n"
                                "          KeyType: HASH\n"
                                "Outputs:\n"
                                "  TableName:\n"
                                "    Value: !Ref TestTable\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_dynamodb_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_dynamodb_stack"],
                },
                {
                    "task_id": "wait_for_value",
                    "operator": "DynamoDBValueSensor",
                    "parameters": {
                        "table_name": "mwaa-test-table",
                        "partition_key_name": "pk",
                        "partition_key_value": "test-key",
                        "attribute_name": "status",
                        "attribute_value": ["complete"],
                    },
                    "upstream_tasks": ["wait_for_dynamodb_stack"],
                },
                {
                    "task_id": "delete_dynamodb_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_value"],
                },
                {
                    "task_id": "wait_for_dynamodb_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_dynamodb_stack"],
                },
            ],
        },
        "opensearch_serverless": {
            "default_params": {"collection_name": "mwaa-test-collection", "stack_name": "mwaa-test-aoss-stack"},
            "tasks": [
                {
                    "task_id": "create_aoss_stack",
                    "operator": "CloudFormationCreateStackOperator",
                    "parameters": {
                        "stack_name": "{{ params.stack_name }}",
                        "cloudformation_parameters": {
                            "StackName": "{{ params.stack_name }}",
                            "TemplateBody": (
                                "AWSTemplateFormatVersion: '2010-09-09'\n"
                                "Resources:\n"
                                "  SecurityPolicy:\n"
                                "    Type: AWS::OpenSearchServerless::SecurityPolicy\n"
                                "    Properties:\n"
                                "      Name: mwaa-test-enc-policy\n"
                                "      Type: encryption\n"
                                "      Policy: '{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/mwaa-test-collection\"]}],\"AWSOwnedKey\":true}'\n"
                                "  NetworkPolicy:\n"
                                "    Type: AWS::OpenSearchServerless::SecurityPolicy\n"
                                "    Properties:\n"
                                "      Name: mwaa-test-net-policy\n"
                                "      Type: network\n"
                                "      Policy: '[{\"Rules\":[{\"ResourceType\":\"collection\",\"Resource\":[\"collection/mwaa-test-collection\"]}],\"AllowFromPublic\":true}]'\n"
                                "  Collection:\n"
                                "    Type: AWS::OpenSearchServerless::Collection\n"
                                "    DependsOn:\n"
                                "      - SecurityPolicy\n"
                                "      - NetworkPolicy\n"
                                "    Properties:\n"
                                "      Name: mwaa-test-collection\n"
                                "      Type: SEARCH\n"
                                "Outputs:\n"
                                "  CollectionName:\n"
                                "    Value: mwaa-test-collection\n"
                            ),
                        },
                    },
                },
                {
                    "task_id": "wait_for_aoss_stack",
                    "operator": "CloudFormationCreateStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["create_aoss_stack"],
                },
                {
                    "task_id": "wait_for_collection",
                    "operator": "OpenSearchServerlessCollectionActiveSensor",
                    "parameters": {"collection_name": "{{ params.collection_name }}"},
                    "upstream_tasks": ["wait_for_aoss_stack"],
                },
                {
                    "task_id": "delete_aoss_stack",
                    "operator": "CloudFormationDeleteStackOperator",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "trigger_rule": "all_done",
                    "upstream_tasks": ["wait_for_collection"],
                },
                {
                    "task_id": "wait_for_aoss_delete",
                    "operator": "CloudFormationDeleteStackSensor",
                    "parameters": {"stack_name": "{{ params.stack_name }}"},
                    "upstream_tasks": ["delete_aoss_stack"],
                },
            ],
        },
    }
