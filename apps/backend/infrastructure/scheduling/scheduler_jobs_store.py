"""CRUD for ``scheduler_jobs`` (tenant-scoped; policy in tool/API handlers)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db


def _uuid(v: Any) -> uuid.UUID | None:
    if v is None:
        return None
    if isinstance(v, uuid.UUID):
        return v
    try:
        return uuid.UUID(str(v).strip())
    except (ValueError, TypeError):
        return None


def user_belongs_to_tenant(user_id: uuid.UUID, tenant_id: int) -> bool:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM users WHERE id = %s AND tenant_id = %s",
                (user_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def insert_job(
    *,
    tenant_id: int,
    created_by_user_id: uuid.UUID,
    execution_user_id: uuid.UUID,
    dashboard_id: uuid.UUID | None,
    execution_target: str,
    title: str | None,
    instructions: str,
    interval_minutes: int,
    enabled: bool = True,
    coding_workflow: dict[str, Any] | None = None,
) -> dict[str, Any]:
    wf = coding_workflow if coding_workflow is not None else {}
    from apps.backend.infrastructure.workspace.workspace_execution import (
        raise_if_workflow_targets_client,
    )

    raise_if_workflow_targets_client(wf)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO scheduler_jobs (
                  tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                  execution_target, title, instructions, interval_minutes, enabled,
                  coding_workflow, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                RETURNING id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                          execution_target, title, instructions, interval_minutes, enabled,
                          coding_workflow, last_run_at, created_at, updated_at
                """,
                (
                    tenant_id,
                    created_by_user_id,
                    execution_user_id,
                    dashboard_id,
                    execution_target,
                    title,
                    instructions,
                    interval_minutes,
                    enabled,
                    Json(wf),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def list_jobs_for_user(
    *,
    tenant_id: int,
    current_user_id: uuid.UUID,
    is_admin: bool,
    dashboard_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """One company's schedules as one account is allowed to see them.

    A plain account gets the rows it owns — created by it **or** running on its
    behalf, since a schedule someone else set up can still be the caller's to look
    at — while an admin of that company gets all of them. The company pinning, the
    archive rule and the dashboard semantics come from :func:`list_jobs_for_scope`;
    the ownership filter is all that is this listing's own.

    Without the owner and company labels: those exist so the admin screen can name
    who set a row up across companies, and this response goes to ordinary members of
    the company too.
    """
    return list_jobs_for_scope(
        tenant_ids=frozenset({int(tenant_id)}),
        dashboard_id=dashboard_id,
        owner_user_id=None if is_admin else current_user_id,
        limit=max(1, min(200, int(limit))),
        include_owner_labels=False,
    )


def list_jobs_for_scope(
    *,
    tenant_ids: frozenset[int] | None,
    dashboard_id: uuid.UUID | None = None,
    include_global: bool = False,
    execution_target: str | None = None,
    enabled: bool | None = None,
    owner_user_id: uuid.UUID | None = None,
    include_owner_labels: bool = True,
    include_archived: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """
    Admin listing across the companies one ``AdminScope`` may reach.

    ``tenant_ids=None`` is the site-admin case — every company, no filter — which
    is what :meth:`AdminScope.tenant_filter` returns. An empty set yields nothing
    rather than everything, so a scope that lost its tenants fails closed.

    Carries the owner and company labels because a cross-company list cannot name
    them from the row alone.

    - dashboard_id=None: list global-only when include_global=True, else all jobs
    - dashboard_id!=None:
        - include_global=True: dashboard-bound + global (dashboard_id IS NULL)
        - include_global=False: only dashboard-bound

    ``owner_user_id`` keeps only the rows that account created or that run on its
    behalf — the member view :func:`list_jobs_for_user` asks for. An admin listing
    leaves it unset, the company set being its bound. ``include_owner_labels`` adds
    the owner and company names, which the cross-company screen needs and the
    single-company member screen must not receive.
    """
    if tenant_ids is not None and not tenant_ids:
        return []
    lim = max(1, min(500, limit))
    params: list[Any] = []
    where = "WHERE TRUE"
    if tenant_ids is not None:
        params.append(sorted(int(t) for t in tenant_ids))
        where += " AND j.tenant_id = ANY(%s)"
    if not include_archived:
        where += " AND j.deleted_at IS NULL"

    if dashboard_id is not None:
        if include_global:
            where += " AND (j.dashboard_id = %s OR j.dashboard_id IS NULL)"
        else:
            where += " AND j.dashboard_id = %s"
        params.append(dashboard_id)
    else:
        if include_global:
            where += " AND j.dashboard_id IS NULL"

    if execution_target is not None and str(execution_target).strip():
        where += " AND j.execution_target = %s"
        params.append(str(execution_target).strip().lower())

    if enabled is not None:
        where += " AND j.enabled = %s"
        params.append(bool(enabled))

    if owner_user_id is not None:
        where += " AND (j.created_by_user_id = %s OR j.execution_user_id = %s)"
        params.extend([owner_user_id, owner_user_id])

    columns = """j.id, j.tenant_id, j.created_by_user_id, j.execution_user_id, j.dashboard_id,
                       j.execution_target, j.title, j.instructions, j.interval_minutes, j.enabled,
                       j.coding_workflow, j.last_run_at, j.deleted_at, j.created_at, j.updated_at"""
    joins = ""
    if include_owner_labels:
        columns += """,
                       cu.display_name AS created_by_display_name, cu.email AS created_by_email,
                       tn.name AS tenant_name"""
        joins = """
                LEFT JOIN users cu ON cu.id = j.created_by_user_id
                LEFT JOIN tenants tn ON tn.id = j.tenant_id"""

    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {columns}
                FROM scheduler_jobs j
                {joins}
                {where}
                ORDER BY j.created_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def list_jobs_for_tenant(
    *,
    tenant_id: int,
    dashboard_id: uuid.UUID | None,
    include_global: bool,
    execution_target: str | None,
    enabled: bool | None,
    include_archived: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Single-company case of :func:`list_jobs_for_scope`."""
    return list_jobs_for_scope(
        tenant_ids=frozenset({int(tenant_id)}),
        dashboard_id=dashboard_id,
        include_global=include_global,
        execution_target=execution_target,
        enabled=enabled,
        include_archived=include_archived,
        limit=limit,
    )


def get_job_any_tenant(job_id: uuid.UUID) -> dict[str, Any] | None:
    """Read one job without a tenant filter.

    Exists only to learn which company a job belongs to before
    :meth:`AdminScope.require_tenant` judges that answer. Every write still runs
    tenant-pinned, so a mistaken read here cannot widen what a statement changes.
    """
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                       execution_target, title, instructions, interval_minutes, enabled,
                       coding_workflow, last_run_at, deleted_at, created_at, updated_at
                FROM scheduler_jobs
                WHERE id = %s
                """,
                (job_id,),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def get_job(job_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                       execution_target, title, instructions, interval_minutes, enabled,
                       coding_workflow, last_run_at, deleted_at, created_at, updated_at
                FROM scheduler_jobs
                WHERE id = %s AND tenant_id = %s
                """,
                (job_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def _writable_job(
    *,
    job_id: uuid.UUID,
    tenant_id: int,
    actor_user_id: uuid.UUID,
    actor_is_admin: bool,
) -> dict[str, Any] | None:
    """The row a mutation may touch, or ``None`` when it may not.

    Owner-or-admin used to be spelled inside every mutation, so a sixth mutation that
    forgot the check would write another user's schedule, and a change to the write
    right had to be made five times. The read stays tenant-pinned — a row outside the
    caller's company answers ``None`` here rather than 403.

    ``actor_is_admin`` is the caller's already-resolved right, never a role read: the
    store does not get to decide who an admin is.
    """
    job = get_job(job_id, tenant_id)
    if job is None:
        return None
    if actor_is_admin:
        return job
    if _uuid(job.get("created_by_user_id")) != actor_user_id:
        return None
    return job


def set_enabled(
    *,
    job_id: uuid.UUID,
    tenant_id: int,
    enabled: bool,
    actor_user_id: uuid.UUID,
    actor_is_admin: bool,
) -> dict[str, Any] | None:
    job = _writable_job(
        job_id=job_id, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_is_admin=actor_is_admin
    )
    if not job:
        return None
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE scheduler_jobs
                SET enabled = %s, updated_at = %s
                WHERE id = %s AND tenant_id = %s
                RETURNING id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                          execution_target, title, instructions, interval_minutes, enabled,
                          coding_workflow, last_run_at, created_at, updated_at
                """,
                (enabled, now, job_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def update_job(
    *,
    job_id: uuid.UUID,
    tenant_id: int,
    actor_user_id: uuid.UUID,
    actor_is_admin: bool,
    title: str | None,
    instructions: str | None,
    interval_minutes: int | None,
    coding_workflow: dict[str, Any] | None,
) -> dict[str, Any] | None:
    job = _writable_job(
        job_id=job_id, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_is_admin=actor_is_admin
    )
    if not job:
        return None
    now = datetime.now(UTC)
    # None means "leave unchanged"
    new_title = job.get("title") if title is None else title
    new_instr = job.get("instructions") if instructions is None else instructions
    new_interval = job.get("interval_minutes") if interval_minutes is None else interval_minutes
    new_wf = job.get("coding_workflow") if coding_workflow is None else coding_workflow
    from apps.backend.infrastructure.workspace.workspace_execution import (
        raise_if_workflow_targets_client,
    )

    if isinstance(new_wf, dict):
        raise_if_workflow_targets_client(new_wf)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE scheduler_jobs
                SET title = %s,
                    instructions = %s,
                    interval_minutes = %s,
                    coding_workflow = %s,
                    updated_at = %s
                WHERE id = %s AND tenant_id = %s
                RETURNING id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                          execution_target, title, instructions, interval_minutes, enabled,
                          coding_workflow, last_run_at, deleted_at, created_at, updated_at
                """,
                (
                    new_title,
                    new_instr,
                    int(new_interval),
                    Json(new_wf if isinstance(new_wf, dict) else {}),
                    now,
                    job_id,
                    tenant_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def archive_job(*, job_id: uuid.UUID, tenant_id: int, actor_user_id: uuid.UUID, actor_is_admin: bool) -> bool:
    job = _writable_job(
        job_id=job_id, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_is_admin=actor_is_admin
    )
    if not job:
        return False
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduler_jobs
                SET deleted_at = %s, enabled = false, updated_at = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (now, now, job_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def unarchive_job(*, job_id: uuid.UUID, tenant_id: int, actor_user_id: uuid.UUID, actor_is_admin: bool) -> bool:
    job = _writable_job(
        job_id=job_id, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_is_admin=actor_is_admin
    )
    if not job:
        return False
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduler_jobs
                SET deleted_at = NULL, updated_at = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (now, job_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def hard_delete_job(*, job_id: uuid.UUID, tenant_id: int, actor_user_id: uuid.UUID, actor_is_admin: bool) -> bool:
    job = _writable_job(
        job_id=job_id, tenant_id=tenant_id, actor_user_id=actor_user_id, actor_is_admin=actor_is_admin
    )
    if not job:
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM scheduler_jobs WHERE id = %s AND tenant_id = %s",
                (job_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def fetch_due_jobs(*, limit: int = 10) -> list[dict[str, Any]]:
    """Enabled jobs whose interval has elapsed since last run (or creation)."""
    lim = max(1, min(50, limit))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, dashboard_id,
                       execution_target, title, instructions, interval_minutes, enabled,
                       coding_workflow, last_run_at, created_at, updated_at
                FROM scheduler_jobs
                WHERE enabled = true
                  AND deleted_at IS NULL
                  AND COALESCE(last_run_at, created_at)
                      + (interval '1 minute' * interval_minutes) <= now()
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (lim,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def mark_job_last_run(*, job_id: uuid.UUID, tenant_id: int) -> bool:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE scheduler_jobs
                SET last_run_at = %s, updated_at = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (now, now, job_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    """JSON-serializable dict for tool responses."""
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
