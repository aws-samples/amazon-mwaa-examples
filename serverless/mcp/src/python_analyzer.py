"""Static analysis of Python DAG files for MWAA Serverless compatibility."""

import ast
import re
from schema import SUPPORTED_OPERATORS, ALLOWED_OPERATOR_VALUES

_SHORT_NAMES = set(SUPPORTED_OPERATORS.keys())
_FQNS = set(SUPPORTED_OPERATORS.values())

# Operators that are never compatible
_BLOCKED_MODULES = {
    "airflow.operators.python": "PythonOperator / @task not supported",
    "airflow.operators.bash": "BashOperator not supported",
}

# Imports that are only warnings (convertible)
_WARN_IMPORTS = {
    "airflow.decorators.dag",
    "airflow.decorators",
}


def analyze_python_dag(source: str) -> dict:
    """Analyze Python DAG source for MWAA Serverless incompatibilities."""
    errors = []
    warnings = []
    info = []

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"compatible": False, "errors": [f"Syntax error: {e}"], "warnings": [], "info": []}

    imports = _collect_imports(tree)
    _check_imports(imports, errors, warnings)
    _check_decorators(tree, errors, warnings)
    _check_operator_usage(tree, imports, errors, warnings, info)
    _check_dynamic_mapping(tree, errors)
    _check_deferrable(tree, errors)
    _check_callbacks(tree, warnings)
    _check_python_callables(tree, errors)
    _check_python_logic(tree, errors)
    _check_dag_construction(tree, info, warnings)

    # Check that the file actually defines a DAG
    has_dag = any("DAG" in i for i in info) or any("@dag" in str(w).lower() for w in warnings)
    if not has_dag:
        errors.append("No DAG definition found — this file does not appear to be an Airflow DAG")

    return {
        "compatible": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def _collect_imports(tree):
    """Collect all imports as {alias: full_module_path}."""
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


def _check_imports(imports, errors, warnings):
    for alias, full in imports.items():
        for blocked_mod, reason in _BLOCKED_MODULES.items():
            if full.startswith(blocked_mod):
                errors.append(f"Import '{full}': {reason}")

        # @task imports from airflow.decorators are errors
        if full.startswith("airflow.decorators"):
            class_name = full.rsplit(".", 1)[-1]
            if class_name == "task" or (class_name == "decorators" and alias == "task"):
                errors.append(f"Import '{full}': @task decorator not supported")
            elif full in _WARN_IMPORTS or class_name == "dag":
                pass  # handled by _check_decorators as warning

        # Check if importing an operator not in the allowlist
        if ".operators." in full or ".sensors." in full:
            class_name = full.rsplit(".", 1)[-1]
            if class_name not in _SHORT_NAMES and full not in _FQNS:
                if class_name[0].isupper():
                    # DummyOperator maps to EmptyOperator — convertible
                    if class_name == "DummyOperator":
                        warnings.append(f"DummyOperator will be converted to EmptyOperator")
                    # Non-AWS provider operators are errors
                    elif "amazon.aws" not in full:
                        errors.append(f"Operator '{class_name}' ({full}) is not an Amazon provider operator — not supported in MWAA Serverless")
                    else:
                        errors.append(f"Operator '{class_name}' ({full}) not in MWAA Serverless operator allowlist")


def _check_decorators(tree, errors, warnings):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                dec_name = _get_decorator_name(dec)
                if dec_name and ("task" in dec_name.lower()):
                    errors.append(f"@{dec_name} decorator on '{node.name}': decorated tasks not supported")
                if dec_name and dec_name == "dag":
                    warnings.append(f"@dag decorator on '{node.name}': will be converted to DAG object in YAML")


def _get_decorator_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _get_decorator_name(node.func)
    return None


def _check_operator_usage(tree, imports, errors, warnings, info):
    """Check operator instantiations."""
    operator_count = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _get_call_name(node)
        if not name:
            continue

        # Resolve through imports
        resolved = imports.get(name, name)
        class_name = resolved.rsplit(".", 1)[-1]

        if class_name in _SHORT_NAMES or resolved in _FQNS:
            operator_count += 1
        elif class_name.endswith("Operator") or class_name.endswith("Sensor"):
            if class_name not in _SHORT_NAMES:
                warnings.append(f"Operator '{class_name}' not in MWAA Serverless allowlist")

    if operator_count > 0:
        info.append(f"Found {operator_count} supported operator instantiation(s)")


def _get_call_name(node):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _check_dynamic_mapping(tree, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("expand", "expand_kwargs", "map"):
                errors.append(f".{node.func.attr}() call: dynamic task mapping not supported")


def _check_deferrable(tree, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "deferrable":
            if isinstance(node.value, ast.Constant) and node.value.value is True:
                errors.append("deferrable=True: deferrable operators not supported")


def _check_callbacks(tree, warnings):
    callback_params = {
        "on_failure_callback", "on_success_callback", "on_retry_callback",
        "on_execute_callback", "on_skipped_callback", "sla_miss_callback",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg in callback_params:
            warnings.append(f"'{node.arg}' is ignored by MWAA Serverless")


def _check_python_callables(tree, errors):
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "python_callable":
            errors.append("python_callable parameter: PythonOperator not supported")


# Modules/functions that indicate Python logic not expressible in YAML
_INCOMPATIBLE_MODULES = {
    "zipfile", "io", "os", "sys", "subprocess", "tempfile", "pathlib",
    "json", "csv", "boto3", "botocore", "requests", "urllib",
}

_INCOMPATIBLE_CALLS = {
    "os.environ.get", "os.environ", "os.getenv", "os.path",
    "open", "exec", "eval", "compile",
}


def _check_python_logic(tree, errors):
    """Detect module-level Python logic that can't be expressed in YAML."""
    for node in ast.iter_child_nodes(tree):
        # Module-level imports of incompatible modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_root = alias.name.split(".")[0]
                if mod_root in _INCOMPATIBLE_MODULES:
                    errors.append(
                        f"Module-level import '{alias.name}': Python logic using {mod_root} "
                        f"cannot be expressed in YAML. Pre-compute values or use params."
                    )
        elif isinstance(node, ast.ImportFrom):
            mod_root = (node.module or "").split(".")[0]
            if mod_root in _INCOMPATIBLE_MODULES:
                errors.append(
                    f"Module-level import from '{node.module}': Python logic using {mod_root} "
                    f"cannot be expressed in YAML. Pre-compute values or use params."
                )

        # Module-level assignments that call functions (e.g., zipfile.ZipFile(), os.environ.get())
        if isinstance(node, ast.Assign):
            for call_node in ast.walk(node.value):
                if isinstance(call_node, ast.Call):
                    call_str = _get_full_call_name(call_node)
                    if call_str:
                        for incompat in _INCOMPATIBLE_CALLS:
                            if incompat in call_str:
                                errors.append(
                                    f"Module-level Python logic '{call_str}(...)': "
                                    f"cannot be expressed in YAML. Pre-compute values or use params."
                                )
                                break


def _get_full_call_name(node):
    """Get dotted call name like 'os.environ.get'."""
    if isinstance(node, ast.Call):
        return _get_full_call_name(node.func)
    if isinstance(node, ast.Attribute):
        parent = _get_full_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


def _check_dag_construction(tree, info, warnings):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _get_call_name(node)
            if name == "DAG":
                info.append("Found DAG() constructor — will need conversion to YAML format")
                # Check for unsupported DAG kwargs
                for kw in node.keywords:
                    if kw.arg in ("catchup", "tags", "access_control", "user_defined_macros",
                                  "user_defined_filters", "render_template_as_native_obj"):
                        warnings.append(f"DAG param '{kw.arg}' is ignored by MWAA Serverless")

    # Check for f-string task IDs and for-loop task generation
    _check_dynamic_task_ids(tree, warnings)


def _check_dynamic_task_ids(tree, warnings):
    """Detect f-string task_id values and for-loop task generation."""
    for node in ast.walk(tree):
        # f-string in task_id keyword
        if isinstance(node, ast.keyword) and node.arg == "task_id":
            if isinstance(node.value, ast.JoinedStr):
                warnings.append("f-string task_id detected: dynamic task IDs require manual conversion")
        # for-loop at module level or inside DAG context that creates operators
        if isinstance(node, ast.For):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    call_name = _get_call_name(child)
                    if call_name and ("Operator" in call_name or "Sensor" in call_name):
                        warnings.append(f"For-loop creating '{call_name}' tasks: dynamic task generation not supported in YAML")
                        break
