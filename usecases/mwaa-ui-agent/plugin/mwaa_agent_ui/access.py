# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Map the signed-in Airflow user's permissions to what the agent may do for them.

Everything here goes through the configured auth manager, so it works the same
with the FAB auth manager on MWAA, the simple auth manager locally, or any
other auth manager.
"""

from __future__ import annotations

from dataclasses import dataclass

from airflow.api_fastapi.app import get_auth_manager
from airflow.api_fastapi.auth.managers.models.base_user import BaseUser
from airflow.api_fastapi.auth.managers.models.resource_details import DagAccessEntity

TIER_READ = "read"
TIER_OPERATE = "operate"


@dataclass(frozen=True)
class UserAccess:
    user_id: str
    user_name: str
    tier: str
    all_dags_readable: bool
    readable_dags: frozenset[str]
    runnable_dags: frozenset[str]
    can_deploy_dags: bool = False
    # Airflow guards these with permissions separate from triggering runs, so they are checked separately.
    can_edit_task_instances: bool = False
    can_edit_runs: bool = False
    # Multi-team mode (Airflow 3.3+ core.multi_team): the teams the user belongs to.
    multi_team: bool = False
    teams: frozenset[str] = frozenset()

    def can_read(self, dag_id: str) -> bool:
        return self.all_dags_readable or dag_id in self.readable_dags


def _multi_team_enabled() -> bool:
    from airflow.configuration import conf

    try:
        return conf.getboolean("core", "multi_team", fallback=False)
    except Exception:  # noqa: BLE001 - unknown option on Airflow < 3.3, or a malformed value
        return False


def _user_teams(auth_manager, user: BaseUser) -> frozenset[str]:
    try:
        return frozenset(auth_manager.get_authorized_teams(user=user, method="GET"))
    except Exception:  # noqa: BLE001 - an auth manager without team support: no team memberships
        return frozenset()


def resolve_access(user: BaseUser) -> UserAccess:
    """Compute the agent tier and DAG scope for ``user``."""
    auth_manager = get_auth_manager()
    readable = frozenset(auth_manager.get_authorized_dag_ids(user=user, method="GET"))
    editable = frozenset(auth_manager.get_authorized_dag_ids(user=user, method="PUT"))
    can_create_runs = auth_manager.is_authorized_dag(
        method="POST", access_entity=DagAccessEntity.RUN, user=user
    )
    multi_team = _multi_team_enabled()

    # Checks without a DAG id ("all DAGs") cannot be trusted in multi-team mode: MWAA's Identity Center docs
    # require every Permission Set to allow DAG GET with no ResourceId (for the home page), and team
    # isolation is applied per DAG. There, scope comes only from the per-DAG lists above.
    all_dags_readable = not multi_team and auth_manager.is_authorized_dag(
        method="GET", user=user
    )

    # Triggering needs both "create DAG runs" and edit rights on the DAG itself.
    runnable = (editable & readable) if can_create_runs else frozenset()

    # A deployed DAG file runs arbitrary code on the workers, and Airflow has no "upload DAG" permission.
    # Require the operate tier, edit rights on every DAG, and permission to create connections, which only
    # Op and Admin have in the FAB auth manager (OP and above in the simple auth manager).
    can_deploy_dags = bool(
        runnable
        and (
            # Multi-team: no-DAG-id checks are not team-scoped, so require edit on every DAG the user sees.
            (readable <= editable)
            if multi_team
            else auth_manager.is_authorized_dag(method="PUT", user=user)
        )
        and auth_manager.is_authorized_connection(method="POST", user=user)
    )
    # Clearing tasks and setting task state need PUT on task instances; setting run state needs PUT on
    # DAG runs. The agent calls Airflow as the built-in User role, which has both, so a custom role without
    # them must not gain them through the agent.
    can_edit_task_instances = bool(runnable) and auth_manager.is_authorized_dag(
        method="PUT", access_entity=DagAccessEntity.TASK_INSTANCE, user=user
    )
    can_edit_runs = bool(runnable) and auth_manager.is_authorized_dag(
        method="PUT", access_entity=DagAccessEntity.RUN, user=user
    )
    return UserAccess(
        user_id=str(user.get_id()),
        user_name=str(user.get_name()),
        tier=TIER_OPERATE if runnable else TIER_READ,
        all_dags_readable=all_dags_readable,
        readable_dags=readable,
        runnable_dags=runnable,
        can_deploy_dags=can_deploy_dags,
        can_edit_task_instances=can_edit_task_instances,
        can_edit_runs=can_edit_runs,
        multi_team=multi_team,
        teams=_user_teams(auth_manager, user) if multi_team else frozenset(),
    )
