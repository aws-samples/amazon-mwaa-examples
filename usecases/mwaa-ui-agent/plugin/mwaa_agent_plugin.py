# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Register the MWAA UI agent in the Airflow UI.

Airflow 3.2 and later: a global "AI Agent" launcher on every page (react_apps, destination
"base"), which follows the page you are on, plus a full-page view under Browse.

Airflow 3.1: the "base" destination and the shared React globals do not exist yet, so the agent
is a full-page view under Browse plus an "AI Agent" tab on DAG, DAG run, and task instance pages.
"""

from typing import ClassVar

from airflow import __version__ as airflow_version
from airflow.plugins_manager import AirflowPlugin
from mwaa_agent_ui.app import app
from packaging.version import Version

URL_PREFIX = "/mwaa-agent"
_BASE = f"{URL_PREFIX}/"
GLOBAL_LAUNCHER_MIN_VERSION = Version("3.2.0")

NAV_VIEW = {
    "name": "AI Agent",
    "href": _BASE,
    "destination": "nav",
    "url_route": "mwaa-agent",
    "category": "browse",
}

TAB_VIEWS = [
    {
        "name": "AI Agent",
        "href": f"{_BASE}?dag_id={{DAG_ID}}",
        "destination": "dag",
        "url_route": "mwaa-agent-dag",
    },
    {
        "name": "AI Agent",
        "href": f"{_BASE}?dag_id={{DAG_ID}}&run_id={{RUN_ID}}",
        "destination": "dag_run",
        "url_route": "mwaa-agent-run",
    },
    {
        "name": "AI Agent",
        "href": f"{_BASE}?dag_id={{DAG_ID}}&run_id={{RUN_ID}}&task_id={{TASK_ID}}&map_index={{MAP_INDEX}}",
        "destination": "task_instance",
        "url_route": "mwaa-agent-ti",
    },
]

GLOBAL_LAUNCHER = {
    # Airflow looks the component up as globalThis[name]; launcher.js registers it under this name.
    "name": "MWAA AI Agent",
    "bundle_url": f"{URL_PREFIX}/static/launcher.js",
    "destination": "base",
    "url_route": "mwaa-agent-launcher",
}


def ui_items(version: str) -> tuple[list[dict], list[dict]]:
    """Return (external_views, react_apps) for an Airflow version."""
    if Version(Version(version).base_version) >= GLOBAL_LAUNCHER_MIN_VERSION:
        return [NAV_VIEW], [GLOBAL_LAUNCHER]
    return [NAV_VIEW, *TAB_VIEWS], []


_EXTERNAL_VIEWS, _REACT_APPS = ui_items(airflow_version)


class MwaaAgentPlugin(AirflowPlugin):  # pylint: disable=too-few-public-methods
    name = "mwaa_agent_plugin"
    fastapi_apps: ClassVar[list[dict]] = [
        {"app": app, "url_prefix": URL_PREFIX, "name": "MWAA UI Agent"}
    ]
    external_views: ClassVar[list[dict]] = _EXTERNAL_VIEWS
    react_apps: ClassVar[list[dict]] = _REACT_APPS
