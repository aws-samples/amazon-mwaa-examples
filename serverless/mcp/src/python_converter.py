"""Convert Python DAG source to MWAA Serverless YAML via AST extraction."""

import ast
import yaml
from schema import SUPPORTED_OPERATORS

_SHORT_NAMES = set(SUPPORTED_OPERATORS.keys())
_FQN_TO_SHORT = {v: k for k, v in SUPPORTED_OPERATORS.items()}

# Operators that can be replaced with EmptyOperator
_REPLACEABLE_WITH_EMPTY = {
    "PythonOperator", "BashOperator", "DummyOperator",
    "ShortCircuitOperator", "BranchPythonOperator",
}

# Known FQN prefix -> short name class extraction
_OPERATOR_MODULES = {
    "airflow.providers.amazon.aws.operators.": True,
    "airflow.providers.amazon.aws.sensors.": True,
}


def convert_python_to_yaml(source: str) -> dict:
    """Extract DAG structure from Python and produce MWAA Serverless YAML."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"yaml": None, "errors": [f"Syntax error: {e}"], "replacements": []}

    imports = _collect_imports(tree)
    dag_id, dag_kwargs = _extract_dag_info(tree)
    tasks, dep_edges = _extract_tasks(tree, imports)

    errors = []
    replacements = []
    yaml_tasks = []

    for t in tasks:
        op = t["operator"]
        resolved = imports.get(op, op)
        short = _resolve_short_name(op, resolved)

        if short and short in _SHORT_NAMES:
            yaml_task = {"task_id": t["task_id"], "operator": short}
        elif op in _REPLACEABLE_WITH_EMPTY or resolved.rsplit(".", 1)[-1] in _REPLACEABLE_WITH_EMPTY:
            orig = resolved.rsplit(".", 1)[-1] if "." in resolved else op
            replacements.append(f"'{t['task_id']}': replaced {orig} with EmptyOperator (needs manual review)")
            yaml_task = {"task_id": t["task_id"], "operator": "EmptyOperator"}
        else:
            class_name = resolved.rsplit(".", 1)[-1] if "." in resolved else op
            errors.append(f"'{t['task_id']}': operator '{class_name}' has no supported equivalent")
            yaml_task = {"task_id": t["task_id"], "operator": f"UNSUPPORTED:{class_name}"}

        # Extract parameters
        params = {k: v for k, v in t.get("kwargs", {}).items()
                  if k not in ("task_id", "dag", "deferrable")}
        if params:
            yaml_task["parameters"] = params

        if t.get("retries") is not None:
            yaml_task["retries"] = t["retries"]
        if t.get("retry_delay") is not None:
            yaml_task["retry_delay"] = t["retry_delay"]
        if t.get("execution_timeout") is not None:
            yaml_task["execution_timeout"] = t["execution_timeout"]
        if t.get("trigger_rule") is not None:
            yaml_task["trigger_rule"] = t["trigger_rule"]

        yaml_tasks.append(yaml_task)

    # Wire up dependencies
    task_id_set = {t["task_id"] for t in yaml_tasks}
    task_map = {t["task_id"]: t for t in yaml_tasks}
    for upstream, downstream in dep_edges:
        if downstream in task_map and upstream in task_id_set:
            task_map[downstream].setdefault("upstream_tasks", [])
            if upstream not in task_map[downstream]["upstream_tasks"]:
                task_map[downstream]["upstream_tasks"].append(upstream)

    # Build DAG YAML
    dag_def = {}
    if dag_kwargs.get("schedule"):
        dag_def["schedule"] = dag_kwargs["schedule"]
    if dag_kwargs.get("description"):
        dag_def["description"] = dag_kwargs["description"]
    if dag_kwargs.get("max_active_runs"):
        dag_def["max_active_runs"] = dag_kwargs["max_active_runs"]

    default_args = dag_kwargs.get("default_args", {})
    if default_args:
        clean_da = {k: v for k, v in default_args.items()
                    if k in ("owner", "retries", "retry_delay", "execution_timeout")}
        if clean_da:
            dag_def["default_args"] = clean_da

    dag_def["tasks"] = yaml_tasks

    # Normalize: convert list tasks to dict format, flatten parameters
    normalized_tasks = {}
    for t in yaml_tasks:
        tid = t.get("task_id", "unknown")
        # Flatten parameters to top level
        params = t.pop("parameters", None)
        if isinstance(params, dict):
            for k, v in params.items():
                if k not in t:
                    t[k] = v
        # Convert upstream_tasks to dependencies
        if "upstream_tasks" in t:
            t["dependencies"] = t.pop("upstream_tasks")
        normalized_tasks[tid] = t
    dag_def["tasks"] = normalized_tasks

    # Resolve short operator names to FQNs
    for tid, tcfg in dag_def.get("tasks", {}).items():
        op = tcfg.get("operator", "")
        if op in SUPPORTED_OPERATORS:
            tcfg["operator"] = SUPPORTED_OPERATORS[op]

    dag_id = dag_id or "converted_dag"
    result_yaml = yaml.dump({dag_id: dag_def}, default_flow_style=False, sort_keys=False)

    return {"yaml": result_yaml, "errors": errors, "replacements": replacements}


def _collect_imports(tree):
    imports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                full = f"{mod}.{alias.name}" if mod else alias.name
                imports[alias.asname or alias.name] = full
    return imports


def _resolve_short_name(local_name, fqn):
    """Resolve to a short operator name from the allowlist."""
    if local_name in _SHORT_NAMES:
        return local_name
    if fqn in _FQN_TO_SHORT:
        return _FQN_TO_SHORT[fqn]
    class_name = fqn.rsplit(".", 1)[-1] if "." in fqn else fqn
    if class_name in _SHORT_NAMES:
        return class_name
    return None


def _extract_dag_info(tree):
    """Extract DAG ID and kwargs from DAG() constructor, context manager, or @dag decorator."""
    # Check for @dag decorator first
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_name = _get_call_name_from_node(dec)
                if dec_name == "dag":
                    kwargs = {}
                    dag_id = node.name  # function name becomes dag_id
                    if isinstance(dec, ast.Call):
                        for kw in dec.keywords:
                            if kw.arg == "dag_id":
                                dag_id = _eval_const(kw.value) or dag_id
                            elif kw.arg in ("schedule", "schedule_interval"):
                                kwargs["schedule"] = _eval_const(kw.value)
                            elif kw.arg == "description":
                                kwargs["description"] = _eval_const(kw.value)
                            elif kw.arg == "max_active_runs":
                                kwargs["max_active_runs"] = _eval_const(kw.value)
                            elif kw.arg == "default_args":
                                kwargs["default_args"] = _eval_dict(kw.value)
                        # Also check positional args
                        if dec.args:
                            dag_id = _eval_const(dec.args[0]) or dag_id
                    return dag_id, kwargs

    # Fall back to DAG() constructor
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if name != "DAG":
            continue

        dag_id = None
        kwargs = {}

        if node.args:
            dag_id = _eval_const(node.args[0])

        for kw in node.keywords:
            if kw.arg == "dag_id":
                dag_id = _eval_const(kw.value)
            elif kw.arg == "schedule" or kw.arg == "schedule_interval":
                kwargs["schedule"] = _eval_const(kw.value)
            elif kw.arg == "description":
                kwargs["description"] = _eval_const(kw.value)
            elif kw.arg == "max_active_runs":
                kwargs["max_active_runs"] = _eval_const(kw.value)
            elif kw.arg == "default_args":
                kwargs["default_args"] = _eval_dict(kw.value)

        return dag_id, kwargs

    return None, {}


def _get_call_name_from_node(node):
    """Get call name from a decorator node (handles Name, Attribute, Call)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _get_call_name_from_node(node.func)
    return None


def _extract_tasks(tree, imports):
    """Extract task instantiations and >> dependency chains."""
    tasks = []
    task_var_map = {}  # variable_name -> task_id
    dep_edges = []  # (upstream_id, downstream_id)

    for node in ast.walk(tree):
        # Task instantiation: var = Operator(task_id=..., ...)
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.value, ast.Call):
                task = _parse_operator_call(node.value, imports)
                if task:
                    var_name = _get_assign_target(node.targets[0])
                    if var_name and task["task_id"]:
                        task_var_map[var_name] = task["task_id"]
                    tasks.append(task)

        # Standalone operator call (no assignment)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            task = _parse_operator_call(node.value, imports)
            if task and task["task_id"]:
                tasks.append(task)

        # >> dependency chains
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.BinOp):
            _extract_deps(node.value, task_var_map, dep_edges)

    return tasks, dep_edges


def _parse_operator_call(call_node, imports):
    """Parse an operator instantiation call."""
    name = _get_call_name(call_node)
    if not name:
        return None

    resolved = imports.get(name, name)
    class_name = resolved.rsplit(".", 1)[-1] if "." in resolved else name

    # Only process things that look like operators
    if not (class_name.endswith("Operator") or class_name.endswith("Sensor")
            or class_name in _SHORT_NAMES or class_name in _REPLACEABLE_WITH_EMPTY
            or class_name == "EmptyOperator"):
        return None

    task_id = None
    kwargs = {}

    for kw in call_node.keywords:
        val = _eval_const(kw.value)
        if kw.arg == "task_id":
            task_id = val
        elif val is not None:
            kwargs[kw.arg] = val

    if not task_id:
        # Try first positional arg
        if call_node.args:
            task_id = _eval_const(call_node.args[0])

    return {
        "task_id": task_id or "unknown_task",
        "operator": name,
        "kwargs": kwargs,
        "retries": kwargs.pop("retries", None),
        "retry_delay": kwargs.pop("retry_delay", None),
        "execution_timeout": kwargs.pop("execution_timeout", None),
        "trigger_rule": kwargs.pop("trigger_rule", None),
    }


def _extract_deps(node, task_var_map, dep_edges):
    """Recursively extract >> chains into (upstream, downstream) edges."""
    if not isinstance(node, ast.BinOp):
        return
    if not isinstance(node.op, ast.RShift):
        return

    left_ids = _resolve_task_refs(node.left, task_var_map)
    right_ids = _resolve_task_refs(node.right, task_var_map)

    for u in left_ids:
        for d in right_ids:
            dep_edges.append((u, d))

    # Recurse left side for chained >> >> >>
    if isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.RShift):
        _extract_deps(node.left, task_var_map, dep_edges)


def _resolve_task_refs(node, task_var_map):
    """Resolve a node to task IDs (handles variables, lists, function calls)."""
    if isinstance(node, ast.Name):
        tid = task_var_map.get(node.id)
        return [tid] if tid else [node.id]
    if isinstance(node, ast.List):
        result = []
        for elt in node.elts:
            result.extend(_resolve_task_refs(elt, task_var_map))
        return result
    if isinstance(node, ast.Call):
        # Could be a direct operator call like EmptyOperator(task_id="x")
        for kw in node.keywords:
            if kw.arg == "task_id":
                val = _eval_const(kw.value)
                if val:
                    return [val]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.RShift):
        # Nested chain — return the rightmost
        return _resolve_task_refs(node.right, task_var_map)
    return []


def _get_call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _get_assign_target(target):
    if isinstance(target, ast.Name):
        return target.id
    return None


def _eval_const(node):
    """Safely evaluate a constant AST node."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_eval_const(e) for e in node.elts]
    if isinstance(node, ast.Dict):
        return _eval_dict(node)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _eval_const(node.operand)
        if isinstance(val, (int, float)):
            return -val
    # For f-strings, template strings, etc. — return a placeholder
    if isinstance(node, ast.JoinedStr):
        return "<f-string: manual conversion needed>"
    return None


def _eval_dict(node):
    if not isinstance(node, ast.Dict):
        return {}
    result = {}
    for k, v in zip(node.keys, node.values):
        key = _eval_const(k)
        val = _eval_const(v)
        if key is not None:
            result[key] = val
    return result
