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
from airflow.api_fastapi.auth.managers.models.resource_details import (
    DagAccessEntity,
    DagDetails,
)

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


def _administers_roles(auth_manager, user: BaseUser) -> bool:
    """True if the user can create and edit Airflow roles, which makes them an administrator in effect.

    Whoever can create and edit roles can grant themselves any permission, so this does not depend on what a
    role is called or on what an operator has put into it. With the FAB auth manager it checks the "Roles"
    permissions, which only the Admin role has by default. The AWS (Identity Center) auth manager answers it
    from its own policies, and an auth manager that cannot answer, or fails, gives no. The simple auth manager
    (the local stack) answers yes for everyone, but there every user is an admin.
    """
    try:
        return all(
            auth_manager.is_authorized_custom_view(
                method=method, resource_name="Roles", user=user
            )
            for method in ("POST", "PUT")
        )
    except Exception:  # noqa: BLE001 - fail closed on an auth manager without this check
        return False


def _user_teams(auth_manager, user: BaseUser) -> frozenset[str]:
    try:
        return frozenset(auth_manager.get_authorized_teams(user=user, method="GET"))
    except Exception:  # noqa: BLE001 - an auth manager without team support: no team memberships
        return frozenset()


def _dag_teams() -> dict[str, str | None]:
    """Every DAG id in the metadata database, with its team on a multi-team environment (otherwise None)."""
    from airflow.models import DagModel
    from airflow.utils.session import create_session
    from sqlalchemy import select

    with create_session() as session:
        if not _multi_team_enabled():
            return dict.fromkeys(session.scalars(select(DagModel.dag_id)))
        from airflow.models.dagbundle import DagBundleModel
        from airflow.models.team import (
            dag_bundle_team_association_table as bundle_teams,
        )

        if (
            "team_name" not in bundle_teams.c
        ):  # before Airflow 3.3, which has no team names
            return dict.fromkeys(session.scalars(select(DagModel.dag_id)))
        rows = session.execute(
            select(DagModel.dag_id, bundle_teams.c.team_name)
            .join(
                DagBundleModel,
                DagModel.bundle_name == DagBundleModel.name,
                isouter=True,
            )
            .join(
                bundle_teams,
                DagBundleModel.name == bundle_teams.c.dag_bundle_name,
                isouter=True,
            )
        ).all()
        return {dag_id: team for dag_id, team in rows}


def _authorized_dags(
    auth_manager,
    user: BaseUser,
    dag_ids: frozenset[str],
    teams: dict[str, str | None],
    method: str,
    access_entity: DagAccessEntity,
) -> frozenset[str]:
    """The DAGs in ``dag_ids`` on which the user may use ``method`` on ``access_entity``, checked DAG by DAG.

    ``batch_is_authorized_dag`` answers for a whole batch (the AWS auth manager sends it to Verified
    Permissions 30 requests at a time), so a batch that is refused is split in half until each refusal is
    pinned to one DAG: one batch when every DAG is allowed. Any error refuses everything.
    """

    def allowed(ids: list[str]) -> bool:
        return auth_manager.batch_is_authorized_dag(
            [
                {
                    "method": method,
                    "access_entity": access_entity,
                    "details": DagDetails(id=dag_id, team_name=teams.get(dag_id)),
                }
                for dag_id in ids
            ],
            user=user,
        )

    result: set[str] = set()
    pending = [sorted(dag_ids)]
    try:
        while pending:
            ids = pending.pop()
            if not ids:
                continue
            if allowed(ids):
                result.update(ids)
            elif len(ids) > 1:
                middle = len(ids) // 2
                pending += [ids[:middle], ids[middle:]]
    except Exception:  # noqa: BLE001 - fail closed on an auth manager that cannot answer
        return frozenset()
    return frozenset(result)


def resolve_access(user: BaseUser) -> UserAccess:
    """Compute the agent tier and DAG scope for ``user``.

    Every grant is checked per DAG. A check without a DAG id says nothing reliable about a given DAG: MWAA's
    Identity Center docs require every Permission Set to allow DAG GET with no ResourceId (for the home page),
    and fine-grained or team policies apply per DAG. Such checks can only narrow what the per-DAG checks give.
    """
    auth_manager = get_auth_manager()
    readable = frozenset(auth_manager.get_authorized_dag_ids(user=user, method="GET"))
    editable = frozenset(auth_manager.get_authorized_dag_ids(user=user, method="PUT"))
    multi_team = _multi_team_enabled()
    try:
        teams = _dag_teams()
    except Exception:  # noqa: BLE001 - without the DAG list, nothing counts as "all DAGs"
        teams = None
    all_dag_ids = frozenset(teams) if teams is not None else None
    teams = teams or {}

    # "All DAGs" opens the whole DAG folder and every Task log stream, so it needs both the global grant and
    # read access to every DAG that exists now, checked per DAG. Never with teams, where folders and log
    # groups mix teams.
    all_dags_readable = bool(
        not multi_team
        and all_dag_ids is not None
        and readable >= all_dag_ids
        and auth_manager.is_authorized_dag(method="GET", user=user)
    )

    # Triggering needs edit rights on the DAG and "create DAG runs" on that DAG.
    runnable = _authorized_dags(
        auth_manager, user, editable & readable, teams, "POST", DagAccessEntity.RUN
    )

    # A deployed DAG file runs arbitrary code on the workers, with the environment's execution role, and Airflow
    # has no "upload DAG" permission. Operate rights are not enough: an operator can give any role to anyone.
    # Deploying needs the operate tier, edit rights on every DAG the user sees (with teams) or on every DAG
    # (without), permission to create connections, and administrator rights (see _administers_roles).
    can_deploy_dags = bool(
        runnable
        and (
            (readable <= editable)
            if multi_team
            else (
                all_dags_readable
                and all_dag_ids is not None
                and editable >= all_dag_ids
                and auth_manager.is_authorized_dag(method="PUT", user=user)
            )
        )
        and auth_manager.is_authorized_connection(method="POST", user=user)
        and _administers_roles(auth_manager, user)
    )
    # Clearing tasks and setting task state need PUT on task instances; setting run state needs PUT on
    # DAG runs. The agent calls Airflow as the built-in User role, which has both, so a custom role without
    # them must not gain them through the agent. The agent gets one flag for all runnable DAGs, so each
    # needs the right on every one of them.
    can_edit_task_instances = bool(runnable) and (
        _authorized_dags(
            auth_manager, user, runnable, teams, "PUT", DagAccessEntity.TASK_INSTANCE
        )
        == runnable
    )
    can_edit_runs = bool(runnable) and (
        _authorized_dags(
            auth_manager, user, runnable, teams, "PUT", DagAccessEntity.RUN
        )
        == runnable
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
