"""Operational functions for MWAA Serverless workflow management."""

import json
import time
import boto3
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("mwaa-serverless")
    return _client


def _iter_tasks(dag):
    """Iterate tasks from a parsed DAG YAML, handling both list and dict formats.
    Also looks inside dag_id-keyed structures."""
    # Direct tasks key
    tasks = dag.get("tasks", [])
    if isinstance(tasks, list):
        yield from tasks
    elif isinstance(tasks, dict):
        for tid, tcfg in tasks.items():
            if isinstance(tcfg, dict):
                t = dict(tcfg)
                t.setdefault("task_id", tid)
                yield t
    # Check for dag_id-keyed structure: {dag_id: {tasks: ...}}
    for key, val in dag.items():
        if key == "tasks":
            continue
        if isinstance(val, dict) and "tasks" in val:
            inner = val["tasks"]
            if isinstance(inner, list):
                yield from inner
            elif isinstance(inner, dict):
                for tid, tcfg in inner.items():
                    if isinstance(tcfg, dict):
                        t = dict(tcfg)
                        t.setdefault("task_id", tid)
                        yield t


def list_workflows(name_contains: str = "", status: str = "") -> dict:
    """List all workflows, optionally filtered by name substring or status."""
    client = _get_client()
    workflows = []
    paginator = client.get_paginator("list_workflows") if hasattr(client, "get_paginator") else None

    if paginator:
        try:
            for page in paginator.paginate():
                workflows.extend(page.get("Workflows", []))
        except Exception:
            resp = client.list_workflows()
            workflows = resp.get("Workflows", [])
    else:
        resp = client.list_workflows()
        workflows = resp.get("Workflows", [])

    # Filter
    if name_contains:
        name_lower = name_contains.lower()
        workflows = [w for w in workflows if name_lower in w.get("Name", "").lower()]
    if status:
        status_upper = status.upper()
        workflows = [w for w in workflows if w.get("WorkflowStatus", "").upper() == status_upper]

    # Compact output
    result = []
    for w in workflows:
        result.append({
            "name": w.get("Name", ""),
            "status": w.get("WorkflowStatus", ""),
            "trigger_mode": w.get("TriggerMode", ""),
            "arn": w.get("WorkflowArn", ""),
            "modified": w.get("ModifiedAt", ""),
        })

    return {"count": len(result), "workflows": result}


def get_workflow(workflow_name: str) -> dict:
    """Get detailed info about a workflow including its DAG YAML definition."""
    client = _get_client()

    # Find the workflow ARN by name
    all_wf = client.list_workflows().get("Workflows", [])
    match = [w for w in all_wf if w.get("Name", "") == workflow_name]
    if not match:
        # Try partial match
        match = [w for w in all_wf if workflow_name.lower() in w.get("Name", "").lower()]
    if not match:
        return {"error": f"No workflow found matching '{workflow_name}'"}

    wf = match[0]
    arn = wf["WorkflowArn"]
    detail = client.get_workflow(WorkflowArn=arn)

    info = {
        "name": detail.get("Name", ""),
        "arn": arn,
        "status": detail.get("WorkflowStatus", ""),
        "trigger_mode": detail.get("TriggerMode", ""),
        "version": detail.get("WorkflowVersion", ""),
        "created": str(detail.get("CreatedAt", "")),
        "modified": str(detail.get("ModifiedAt", "")),
        "execution_role_arn": detail.get("RoleArn", detail.get("ExecutionRoleArn", "")),
    }

    # Try to get the DAG definition from S3
    s3_loc = detail.get("DefinitionS3Location", {})
    if s3_loc:
        info["definition_s3"] = {"bucket": s3_loc.get("Bucket", ""), "key": s3_loc.get("ObjectKey", "")}
        try:
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=s3_loc["Bucket"], Key=s3_loc["ObjectKey"])
            yaml_content = obj["Body"].read().decode("utf-8")
            info["dag_yaml"] = yaml_content
            # Extract operators used
            try:
                dag = yaml.safe_load(yaml_content)
                operators = set()
                for t in _iter_tasks(dag):
                    op = t.get("operator", "")
                    if op:
                        operators.add(op)
                info["operators_used"] = sorted(operators)
            except Exception:
                pass
        except Exception as e:
            info["dag_yaml_error"] = str(e)

    return info


def start_workflow_run(workflow_name: str) -> dict:
    """Start a workflow run by name."""
    client = _get_client()

    all_wf = client.list_workflows().get("Workflows", [])
    match = [w for w in all_wf if w.get("Name", "") == workflow_name]
    if not match:
        match = [w for w in all_wf if workflow_name.lower() in w.get("Name", "").lower()]
    if not match:
        return {"error": f"No workflow found matching '{workflow_name}'"}

    arn = match[0]["WorkflowArn"]
    resp = client.start_workflow_run(WorkflowArn=arn)

    return {
        "workflow_name": match[0].get("Name", ""),
        "workflow_arn": arn,
        "run_id": resp.get("RunId", resp.get("WorkflowRunId", "")),
        "status": "STARTED",
    }


def get_workflow_run_status(workflow_name: str, run_id: str = "") -> dict:
    """Get the status of a workflow run. If no run_id, gets the latest run."""
    client = _get_client()

    all_wf = client.list_workflows().get("Workflows", [])
    match = [w for w in all_wf if w.get("Name", "") == workflow_name]
    if not match:
        match = [w for w in all_wf if workflow_name.lower() in w.get("Name", "").lower()]
    if not match:
        return {"error": f"No workflow found matching '{workflow_name}'"}

    arn = match[0]["WorkflowArn"]

    if not run_id:
        # Get latest run
        try:
            runs = client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            if not runs:
                return {"workflow_name": match[0].get("Name", ""), "message": "No runs found"}
            # Sort by created time descending
            runs.sort(
                key=lambda r: str(r.get("RunDetailSummary", {}).get("CreatedOn", r.get("StartedAt", ""))),
                reverse=True,
            )
            run_id = runs[0].get("RunId", "")
        except Exception as e:
            return {"error": f"Failed to list runs: {str(e)}"}

    try:
        run = client.get_workflow_run(WorkflowArn=arn, RunId=run_id)
    except Exception as e:
        return {"error": f"Failed to get run: {str(e)}"}

    detail = run.get("RunDetail", {})
    result = {
        "workflow_name": match[0].get("Name", ""),
        "run_id": run_id,
        "status": detail.get("RunState", run.get("Status", "")),
        "started_at": str(detail.get("CreatedAt", run.get("StartedAt", ""))),
        "ended_at": str(detail.get("ModifiedAt", run.get("EndedAt", ""))),
    }

    # Include error message if present
    if detail.get("ErrorMessage"):
        result["error_message"] = detail["ErrorMessage"]

    # Include task details if available
    tasks = detail.get("TaskInstances", [])
    if tasks:
        if isinstance(tasks[0], str):
            result["task_instances"] = tasks
        else:
            result["tasks"] = []
            for t in tasks:
                task_info = {
                    "task_id": t.get("TaskId", t.get("task_id", "")),
                    "status": t.get("Status", t.get("state", "")),
                }
                if t.get("Error") or t.get("ErrorMessage"):
                    task_info["error"] = t.get("Error", t.get("ErrorMessage", ""))
                result["tasks"].append(task_info)

    # Include failure reason if failed
    if run.get("FailureReason"):
        result["failure_reason"] = run["FailureReason"]

    return result


def stop_workflow_run(workflow_name: str, run_id: str = "") -> dict:
    """Stop a running workflow. If no run_id, stops the latest active run."""
    client = _get_client()

    all_wf = client.list_workflows().get("Workflows", [])
    match = [w for w in all_wf if w.get("Name", "") == workflow_name]
    if not match:
        match = [w for w in all_wf if workflow_name.lower() in w.get("Name", "").lower()]
    if not match:
        return {"error": f"No workflow found matching '{workflow_name}'"}

    arn = match[0]["WorkflowArn"]

    if not run_id:
        try:
            runs = client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            active = [
                r for r in runs
                if r.get("RunDetailSummary", {}).get("Status", "") in ("RUNNING", "STARTING", "QUEUED")
            ]
            if not active:
                return {"message": "No active runs to stop"}
            active.sort(
                key=lambda r: str(r.get("RunDetailSummary", {}).get("CreatedOn", "")),
                reverse=True,
            )
            run_id = active[0].get("RunId", "")
        except Exception as e:
            return {"error": f"Failed to list runs: {str(e)}"}

    client.stop_workflow_run(WorkflowArn=arn, RunId=run_id)
    return {"workflow_name": match[0].get("Name", ""), "run_id": run_id, "status": "STOPPING"}


def find_workflows_using_service(service_keyword: str) -> dict:
    """Find workflows that use operators for a specific AWS service by inspecting DAG YAML definitions."""
    client = _get_client()

    # Map common service names to operator substrings (short names + FQN fragments)
    service_map = {
        "step_functions": ["StepFunction", "step_function"],
        "step functions": ["StepFunction", "step_function"],
        "sfn": ["StepFunction", "step_function"],
        "s3": ["S3", ".s3."],
        "glue": ["Glue", ".glue."],
        "athena": ["Athena", ".athena."],
        "bedrock": ["Bedrock", ".bedrock."],
        "lambda": ["Lambda", ".lambda_function."],
        "emr": ["Emr", ".emr."],
        "batch": ["Batch", ".batch."],
        "ecs": ["Ecs", ".ecs."],
        "eks": ["Eks", ".eks."],
        "sqs": ["Sqs", ".sqs."],
        "sns": ["Sns", ".sns."],
        "redshift": ["Redshift", ".redshift"],
        "sagemaker": ["SageMaker", ".sagemaker."],
        "rds": ["Rds", ".rds."],
        "ec2": ["Ec2", ".ec2."],
        "eventbridge": ["EventBridge", ".eventbridge."],
        "cloudformation": ["CloudFormation", ".cloud_formation."],
        "comprehend": ["Comprehend", ".comprehend."],
        "dms": ["Dms", ".dms."],
        "neptune": ["Neptune", ".neptune."],
        "dynamodb": ["DynamoDB", ".dynamodb."],
        "datasync": ["DataSync", ".datasync."],
        "glacier": ["Glacier", ".glacier."],
        "appflow": ["Appflow", ".appflow."],
        "quicksight": ["QuickSight", ".quicksight."],
        "opensearch": ["OpenSearch", ".opensearch."],
        "kinesis": ["Kinesis", ".kinesis."],
    }

    keywords = service_map.get(service_keyword.lower(), [service_keyword])
    all_wf = client.list_workflows().get("Workflows", [])

    def _inspect(wf):
        try:
            arn = wf["WorkflowArn"]
            detail = boto3.client("mwaa-serverless").get_workflow(WorkflowArn=arn)
            s3_loc = detail.get("DefinitionS3Location", {})
            if not s3_loc:
                return None
            obj = boto3.client("s3").get_object(Bucket=s3_loc["Bucket"], Key=s3_loc["ObjectKey"])
            dag = yaml.safe_load(obj["Body"].read().decode("utf-8"))
            found = [
                {"task_id": t.get("task_id", ""), "operator": t.get("operator", "")}
                for t in _iter_tasks(dag)
                if any(kw.lower() in t.get("operator", "").lower() for kw in keywords)
            ]
            if found:
                return {"name": wf.get("Name", ""), "arn": arn, "matching_tasks": found}
        except Exception:
            pass
        return None

    matches = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_inspect, wf): wf for wf in all_wf}
        for f in as_completed(futures):
            result = f.result()
            if result:
                matches.append(result)

    return {"service": service_keyword, "count": len(matches), "workflows": matches}


def _resolve_workflow_arn(workflow_name: str) -> tuple:
    """Resolve a workflow name to (arn, name, all_workflows). Returns (None, error_msg, None) on failure."""
    client = _get_client()
    all_wf = client.list_workflows().get("Workflows", [])
    match = [w for w in all_wf if w.get("Name", "") == workflow_name]
    if not match:
        match = [w for w in all_wf if workflow_name.lower() in w.get("Name", "").lower()]
    if not match:
        return None, f"No workflow found matching '{workflow_name}'", None
    return match[0]["WorkflowArn"], match[0].get("Name", ""), all_wf


def deploy_and_run(workflow_name: str, yaml_content: str, s3_bucket: str, execution_role_arn: str, s3_key: str = "") -> dict:
    """Upload YAML to S3, create or update the workflow, and start a run — all in one call."""
    client = _get_client()
    s3 = boto3.client("s3")

    if not s3_key:
        s3_key = f"workflows/{workflow_name}.yaml"

    # 1. Upload YAML to S3
    try:
        s3.put_object(Bucket=s3_bucket, Key=s3_key, Body=yaml_content.encode("utf-8"))
    except Exception as e:
        return {"error": f"S3 upload failed: {str(e)}"}

    # 2. Create or update workflow
    s3_loc = {"Bucket": s3_bucket, "ObjectKey": s3_key}
    try:
        resp = client.create_workflow(
            Name=workflow_name,
            DefinitionS3Location=s3_loc,
            RoleArn=execution_role_arn,
        )
        arn = resp.get("WorkflowArn", "")
        action = "created"
    except client.exceptions.ConflictException:
        # Already exists — find ARN and update
        all_wf = client.list_workflows().get("Workflows", [])
        existing = [w for w in all_wf if w.get("Name", "") == workflow_name]
        if not existing:
            return {"error": f"Workflow '{workflow_name}' conflict but not found in list"}
        arn = existing[0]["WorkflowArn"]
        try:
            client.update_workflow(
                WorkflowArn=arn,
                DefinitionS3Location=s3_loc,
                RoleArn=execution_role_arn,
            )
            action = "updated"
        except Exception as e:
            return {"error": f"Update failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Create failed: {str(e)}"}

    # 3. Start a run
    try:
        run_resp = client.start_workflow_run(WorkflowArn=arn)
        run_id = run_resp.get("RunId", "")
    except Exception as e:
        return {
            "workflow_name": workflow_name, "workflow_arn": arn, "action": action,
            "s3_location": s3_loc, "error": f"Workflow {action} but start failed: {str(e)}",
        }

    return {
        "workflow_name": workflow_name,
        "workflow_arn": arn,
        "action": action,
        "s3_location": s3_loc,
        "run_id": run_id,
        "status": "STARTED",
    }


def poll_workflow_run(workflow_name: str, run_id: str = "", max_seconds: int = 25) -> dict:
    """Poll a workflow run until terminal state or timeout. Returns final status with error details."""
    client = _get_client()

    arn, name, _ = _resolve_workflow_arn(workflow_name)
    if arn is None:
        return {"error": name}

    # Resolve run_id if not provided
    if not run_id:
        try:
            runs = client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            if not runs:
                return {"workflow_name": name, "message": "No runs found"}
            runs.sort(
                key=lambda r: str(r.get("RunDetailSummary", {}).get("CreatedOn", "")),
                reverse=True,
            )
            run_id = runs[0].get("RunId", "")
        except Exception as e:
            return {"error": f"Failed to list runs: {str(e)}"}

    terminal_states = {"SUCCESS", "FAILED", "STOPPED", "TIMEOUT"}
    start_time = time.time()
    poll_interval = 3
    last_status = {}

    while time.time() - start_time < max_seconds:
        try:
            run = client.get_workflow_run(WorkflowArn=arn, RunId=run_id)
            detail = run.get("RunDetail", {})
            state = detail.get("RunState", "")

            last_status = {
                "workflow_name": name,
                "run_id": run_id,
                "status": state,
                "started_at": str(detail.get("CreatedAt", "")),
                "duration": detail.get("Duration"),
            }

            if detail.get("ErrorMessage"):
                last_status["error_message"] = detail["ErrorMessage"]

            tasks = detail.get("TaskInstances", [])
            if tasks:
                last_status["task_instances"] = tasks if isinstance(tasks[0], str) else [
                    t.get("TaskId", "") for t in tasks
                ]

            if state in terminal_states:
                last_status["completed"] = True
                if detail.get("CompletedOn"):
                    last_status["ended_at"] = str(detail["CompletedOn"])
                return last_status

        except Exception as e:
            last_status = {"workflow_name": name, "run_id": run_id, "error": str(e)}

        time.sleep(poll_interval)

    last_status["completed"] = False
    last_status["message"] = f"Still running after {max_seconds}s polling. Call again to continue polling."
    return last_status


def _get_task_error_logs(workflow_arn: str, run_id: str, max_lines: int = 5) -> list:
    """Pull error/warning log lines from CloudWatch for a failed run's tasks."""
    logs_client = boto3.client("logs")
    # Extract workflow ID from ARN (last segment after workflow/)
    wf_id = workflow_arn.rsplit("/", 1)[-1] if "/" in workflow_arn else workflow_arn
    log_group = f"/aws/mwaa-serverless/{wf_id}/"

    task_logs = []
    try:
        # Find log streams for this run
        streams = logs_client.describe_log_streams(
            logGroupName=log_group,
            logStreamNamePrefix=f"workflow_id={wf_id}/run_id={run_id}/",
            limit=20,
        ).get("logStreams", [])

        for stream in streams:
            stream_name = stream.get("logStreamName", "")
            # Extract task_id from stream name
            task_id = ""
            for part in stream_name.split("/"):
                if part.startswith("task_id="):
                    task_id = part.split("=", 1)[1]

            try:
                events = logs_client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream_name,
                    limit=50,
                ).get("events", [])

                # Extract error and warning lines
                error_lines = []
                for evt in events:
                    msg = evt.get("message", "")
                    try:
                        parsed = json.loads(msg)
                        level = parsed.get("level", "")
                        if level == "error":
                            entry = parsed.get("event", "")
                            # Include error_detail if present (has stack trace info)
                            detail = parsed.get("error_detail", "")
                            if detail and isinstance(detail, list):
                                exc_parts = []
                                for d in detail:
                                    if d.get("exc_value"):
                                        exc_parts.append(d["exc_value"])
                                if exc_parts:
                                    entry += " | " + "; ".join(exc_parts)
                            if entry:
                                error_lines.append(entry)
                    except (json.JSONDecodeError, TypeError):
                        lower = msg.lower()
                        if "error" in lower or "exception" in lower or "failed" in lower:
                            error_lines.append(msg.strip()[:200])

                if error_lines:
                    task_logs.append({
                        "task_id": task_id,
                        "errors": error_lines[:max_lines],
                    })
            except Exception:
                continue
    except Exception:
        pass

    return task_logs


def get_failed_runs_summary(name_contains: str = "", hours_back: int = 24, analyze: bool = True) -> dict:
    """Scan workflows for recent failed runs, collect errors + CloudWatch logs, and optionally analyze with Bedrock."""
    client = _get_client()
    from datetime import datetime, timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    # Get workflows
    all_wf = client.list_workflows().get("Workflows", [])
    if name_contains:
        name_lower = name_contains.lower()
        all_wf = [w for w in all_wf if name_lower in w.get("Name", "").lower()]

    def _check_workflow(wf):
        """Check a single workflow for failed runs and pull logs."""
        try:
            wf_client = boto3.client("mwaa-serverless")
            arn = wf["WorkflowArn"]
            runs = wf_client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            failures = []
            for r in runs:
                summary = r.get("RunDetailSummary", {})
                if summary.get("Status") != "FAILED":
                    continue
                created = summary.get("CreatedOn", "")
                if created and datetime.fromisoformat(str(created)) < cutoff:
                    continue
                run_id = r.get("RunId", "")
                try:
                    detail_resp = wf_client.get_workflow_run(WorkflowArn=arn, RunId=run_id)
                    detail = detail_resp.get("RunDetail", {})
                    failure = {
                        "run_id": run_id,
                        "created": str(created),
                        "error_message": detail.get("ErrorMessage", "No error message"),
                    }
                    # Pull CloudWatch task logs
                    task_logs = _get_task_error_logs(arn, run_id)
                    if task_logs:
                        failure["task_logs"] = task_logs
                    failures.append(failure)
                except Exception:
                    failures.append({
                        "run_id": run_id,
                        "created": str(created),
                        "error_message": "Could not retrieve run details",
                    })
            if failures:
                return {"name": wf.get("Name", ""), "arn": arn, "failed_runs": failures}
        except Exception:
            pass
        return None

    # Parallel scan
    failed_workflows = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_check_workflow, wf): wf for wf in all_wf}
        for f in as_completed(futures):
            result = f.result()
            if result:
                failed_workflows.append(result)

    # Bedrock analysis
    if analyze and failed_workflows:
        try:
            bedrock = boto3.client("bedrock-runtime")
            failure_text = json.dumps(failed_workflows, indent=2, default=str)
            if len(failure_text) > 12000:
                failure_text = failure_text[:12000] + "\n... (truncated)"

            prompt = (
                "You are an MWAA Serverless workflow debugging expert. Analyze these failed workflow runs. "
                "Each failure includes the error message AND CloudWatch task logs showing the actual errors "
                "from task execution. Use the task_logs to identify the real root cause — not just the "
                "generic error message. For each failure provide: (1) root cause from the logs, "
                "(2) specific suggested fix. Be concise — 2-3 sentences per workflow.\n\n"
                f"Failed runs with logs:\n{failure_text}"
            )

            resp = bedrock.invoke_model(
                modelId=os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-4-5-20250620-v1:0"),
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}],
                }),
            )
            analysis = json.loads(resp["body"].read().decode("utf-8"))
            ai_analysis = analysis.get("content", [{}])[0].get("text", "")
        except Exception as e:
            ai_analysis = f"Bedrock analysis unavailable: {str(e)}"
    else:
        ai_analysis = None

    result = {
        "hours_back": hours_back,
        "workflows_scanned": len(all_wf),
        "workflows_with_failures": len(failed_workflows),
        "failures": failed_workflows,
    }
    if ai_analysis:
        result["analysis"] = ai_analysis

    return result


def delete_workflows(name_contains: str = "", not_run_in_days: int = 0, dry_run: bool = True) -> dict:
    """Delete workflows matching criteria. Supports filtering by name and by inactivity period.
    Always does a dry run first unless dry_run=False."""
    client = _get_client()
    from datetime import datetime, timezone, timedelta

    all_wf = client.list_workflows().get("Workflows", [])

    # Filter by name
    if name_contains:
        name_lower = name_contains.lower()
        all_wf = [w for w in all_wf if name_lower in w.get("Name", "").lower()]

    # Filter by inactivity — check last run date
    if not_run_in_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=not_run_in_days)
        inactive = []

        def _check_inactive(wf):
            try:
                wf_client = boto3.client("mwaa-serverless")
                arn = wf["WorkflowArn"]
                runs = wf_client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
                if not runs:
                    # Never run — include it
                    return wf
                latest = max(
                    str(r.get("RunDetailSummary", {}).get("CreatedOn", ""))
                    for r in runs
                )
                if latest and datetime.fromisoformat(latest) < cutoff:
                    return wf
            except Exception:
                pass
            return None

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = {pool.submit(_check_inactive, wf): wf for wf in all_wf}
            for f in as_completed(futures):
                result = f.result()
                if result:
                    inactive.append(result)
        all_wf = inactive

    targets = [{"name": w.get("Name", ""), "arn": w["WorkflowArn"]} for w in all_wf]

    if dry_run:
        return {
            "dry_run": True,
            "count": len(targets),
            "workflows_to_delete": targets,
            "message": "Set dry_run=false to actually delete these workflows.",
        }

    # Actually delete
    results = []
    for t in targets:
        try:
            client.delete_workflow(WorkflowArn=t["arn"])
            results.append({"name": t["name"], "status": "deleted"})
        except Exception as e:
            results.append({"name": t["name"], "status": "error", "error": str(e)})

    return {"dry_run": False, "count": len(results), "results": results}


def list_runs(name_contains: str = "", status: str = "", hours_back: int = 0) -> dict:
    """List workflow runs with optional filters. Can filter by workflow name, run status, and time window."""
    client = _get_client()
    from datetime import datetime, timezone, timedelta

    cutoff = None
    if hours_back > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

    all_wf = client.list_workflows().get("Workflows", [])
    if name_contains:
        name_lower = name_contains.lower()
        all_wf = [w for w in all_wf if name_lower in w.get("Name", "").lower()]

    status_upper = status.upper() if status else ""

    def _get_runs(wf):
        try:
            wf_client = boto3.client("mwaa-serverless")
            arn = wf["WorkflowArn"]
            runs = wf_client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            matched = []
            for r in runs:
                summary = r.get("RunDetailSummary", {})
                run_status = summary.get("Status", "")
                created = summary.get("CreatedOn", "")

                if status_upper and run_status.upper() != status_upper:
                    continue
                if cutoff and created:
                    try:
                        if datetime.fromisoformat(str(created)) < cutoff:
                            continue
                    except Exception:
                        pass

                matched.append({
                    "run_id": r.get("RunId", ""),
                    "status": run_status,
                    "created": str(created),
                    "started": str(summary.get("StartedAt", "")),
                    "ended": str(summary.get("EndedAt", "")),
                })
            if matched:
                return {"name": wf.get("Name", ""), "runs": matched}
        except Exception:
            pass
        return None

    all_runs = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_get_runs, wf): wf for wf in all_wf}
        for f in as_completed(futures):
            result = f.result()
            if result:
                all_runs.append(result)

    # Summary counts
    total_runs = sum(len(w["runs"]) for w in all_runs)
    status_counts = {}
    for w in all_runs:
        for r in w["runs"]:
            s = r["status"]
            status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "workflows_with_runs": len(all_runs),
        "total_runs": total_runs,
        "status_summary": status_counts,
        "workflows": all_runs,
    }


def get_workflow_summary(workflow_name: str) -> dict:
    """Compact workflow overview without the full YAML — name, status, last run, operator count."""
    client = _get_client()

    arn, name, _ = _resolve_workflow_arn(workflow_name)
    if arn is None:
        return {"error": name}

    detail = client.get_workflow(WorkflowArn=arn)

    info = {
        "name": detail.get("Name", ""),
        "status": detail.get("WorkflowStatus", ""),
        "trigger_mode": detail.get("TriggerMode", ""),
        "created": str(detail.get("CreatedAt", "")),
        "modified": str(detail.get("ModifiedAt", "")),
        "execution_role_arn": detail.get("RoleArn", ""),
    }

    # Get operator count from S3
    s3_loc = detail.get("DefinitionS3Location", {})
    if s3_loc:
        info["definition_s3"] = f"s3://{s3_loc.get('Bucket','')}/{s3_loc.get('ObjectKey','')}"
        try:
            s3 = boto3.client("s3")
            obj = s3.get_object(Bucket=s3_loc["Bucket"], Key=s3_loc["ObjectKey"])
            dag = yaml.safe_load(obj["Body"].read().decode("utf-8"))
            operators = {}
            for t in _iter_tasks(dag):
                op = t.get("operator", "")
                if op:
                    short = op.rsplit(".", 1)[-1] if "." in op else op
                    operators[short] = operators.get(short, 0) + 1
            info["task_count"] = sum(operators.values())
            info["operators"] = operators
        except Exception:
            pass

    # Get latest run status
    try:
        runs = client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
        if runs:
            runs.sort(
                key=lambda r: str(r.get("RunDetailSummary", {}).get("CreatedOn", "")),
                reverse=True,
            )
            latest = runs[0]
            summary = latest.get("RunDetailSummary", {})
            info["latest_run"] = {
                "run_id": latest.get("RunId", ""),
                "status": summary.get("Status", ""),
                "created": str(summary.get("CreatedOn", "")),
            }
            # Count runs by status
            status_counts = {}
            for r in runs:
                s = r.get("RunDetailSummary", {}).get("Status", "")
                status_counts[s] = status_counts.get(s, 0) + 1
            info["run_history"] = status_counts
            info["total_runs"] = len(runs)
    except Exception:
        pass

    return info


def bulk_status(name_contains: str = "", names: list = None) -> dict:
    """Get status of multiple workflows with their latest run in one call."""
    client = _get_client()

    all_wf = client.list_workflows().get("Workflows", [])

    if names:
        names_lower = [n.lower() for n in names]
        all_wf = [w for w in all_wf if any(n in w.get("Name", "").lower() for n in names_lower)]
    elif name_contains:
        name_lower = name_contains.lower()
        all_wf = [w for w in all_wf if name_lower in w.get("Name", "").lower()]

    def _get_status(wf):
        try:
            wf_client = boto3.client("mwaa-serverless")
            arn = wf["WorkflowArn"]
            info = {"name": wf.get("Name", ""), "workflow_status": wf.get("WorkflowStatus", "")}
            runs = wf_client.list_workflow_runs(WorkflowArn=arn).get("WorkflowRuns", [])
            if runs:
                runs.sort(
                    key=lambda r: str(r.get("RunDetailSummary", {}).get("CreatedOn", "")),
                    reverse=True,
                )
                s = runs[0].get("RunDetailSummary", {})
                info["latest_run"] = {
                    "status": s.get("Status", ""),
                    "created": str(s.get("CreatedOn", "")),
                }
            else:
                info["latest_run"] = None
            return info
        except Exception:
            return {"name": wf.get("Name", ""), "error": "Failed to get status"}

    results = []
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(_get_status, wf): wf for wf in all_wf}
        for f in as_completed(futures):
            results.append(f.result())

    # Sort by name
    results.sort(key=lambda r: r.get("name", ""))

    return {"count": len(results), "workflows": results}


def redeploy_workflow(workflow_name: str, yaml_content: str, s3_bucket: str = "", s3_key: str = "") -> dict:
    """Update an existing workflow's YAML and start a new run. Reuses existing S3 location and role if not specified."""
    client = _get_client()

    arn, name, _ = _resolve_workflow_arn(workflow_name)
    if arn is None:
        return {"error": name}

    # Get existing workflow details for defaults
    detail = client.get_workflow(WorkflowArn=arn)
    existing_s3 = detail.get("DefinitionS3Location", {})
    role_arn = detail.get("RoleArn", "")

    if not s3_bucket:
        s3_bucket = existing_s3.get("Bucket", "")
    if not s3_key:
        s3_key = existing_s3.get("ObjectKey", "")

    if not s3_bucket or not s3_key:
        return {"error": "Could not determine S3 location. Provide s3_bucket and s3_key."}

    # Upload new YAML
    s3 = boto3.client("s3")
    try:
        s3.put_object(Bucket=s3_bucket, Key=s3_key, Body=yaml_content.encode("utf-8"))
    except Exception as e:
        return {"error": f"S3 upload failed: {str(e)}"}

    # Update workflow
    try:
        client.update_workflow(
            WorkflowArn=arn,
            DefinitionS3Location={"Bucket": s3_bucket, "ObjectKey": s3_key},
            RoleArn=role_arn,
        )
    except Exception as e:
        return {"error": f"Update failed: {str(e)}"}

    # Start run
    try:
        run_resp = client.start_workflow_run(WorkflowArn=arn)
        run_id = run_resp.get("RunId", "")
    except Exception as e:
        return {"workflow_name": name, "action": "updated", "error": f"Update succeeded but start failed: {str(e)}"}

    return {
        "workflow_name": name,
        "workflow_arn": arn,
        "action": "redeployed",
        "s3_location": {"bucket": s3_bucket, "key": s3_key},
        "run_id": run_id,
        "status": "STARTED",
    }


def compare_versions(workflow_name: str) -> dict:
    """Compare the latest two versions of a workflow to show what changed."""
    client = _get_client()

    arn, name, _ = _resolve_workflow_arn(workflow_name)
    if arn is None:
        return {"error": name}

    versions = client.list_workflow_versions(WorkflowArn=arn).get("WorkflowVersions", [])
    if len(versions) < 2:
        return {"workflow_name": name, "message": "Only one version exists, nothing to compare."}

    # Sort by created date descending
    versions.sort(key=lambda v: str(v.get("CreatedAt", "")), reverse=True)
    latest = versions[0]
    previous = versions[1]

    s3 = boto3.client("s3")
    yamls = {}
    for label, ver in [("latest", latest), ("previous", previous)]:
        s3_loc = ver.get("DefinitionS3Location", {})
        try:
            obj = s3.get_object(Bucket=s3_loc["Bucket"], Key=s3_loc["ObjectKey"])
            yamls[label] = obj["Body"].read().decode("utf-8")
        except Exception:
            yamls[label] = None

    result = {
        "workflow_name": name,
        "latest_version": {
            "version": latest.get("WorkflowVersion", ""),
            "created": str(latest.get("CreatedAt", "")),
            "s3": f"s3://{latest.get('DefinitionS3Location',{}).get('Bucket','')}/{latest.get('DefinitionS3Location',{}).get('ObjectKey','')}",
        },
        "previous_version": {
            "version": previous.get("WorkflowVersion", ""),
            "created": str(previous.get("CreatedAt", "")),
            "s3": f"s3://{previous.get('DefinitionS3Location',{}).get('Bucket','')}/{previous.get('DefinitionS3Location',{}).get('ObjectKey','')}",
        },
        "total_versions": len(versions),
    }

    if yamls.get("latest") and yamls.get("previous"):
        if yamls["latest"] == yamls["previous"]:
            result["diff"] = "No changes in YAML content (S3 location may have changed)."
        else:
            # Compute a simple line diff
            import difflib
            diff = list(difflib.unified_diff(
                yamls["previous"].splitlines(keepends=True),
                yamls["latest"].splitlines(keepends=True),
                fromfile=f"v:{previous.get('WorkflowVersion','')}",
                tofile=f"v:{latest.get('WorkflowVersion','')}",
                n=2,
            ))
            result["diff"] = "".join(diff[:100])  # Cap at 100 lines
            result["diff_lines"] = len(diff)
    else:
        result["diff"] = "Could not retrieve one or both YAML definitions."

    return result
