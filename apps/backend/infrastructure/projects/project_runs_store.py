"""CRUD for ``project_runs`` (tenant-scoped).

`project_runs` is a one-shot execution queue for coding-agent runs on a workspace.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


def insert_run(
    *,
    tenant_id: int,
    created_by_user_id: uuid.UUID,
    execution_user_id: uuid.UUID,
    scheduler_job_id: uuid.UUID | None,
    dashboard_id: uuid.UUID | None,
    project_row_id: str | None,
    project_title: str | None,
    execution_target: str,
    instructions: str,
    coding_workflow: dict[str, Any] | None,
) -> dict[str, Any]:
    wf = coding_workflow if coding_workflow is not None else {}
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO project_runs (
                  tenant_id, created_by_user_id, execution_user_id,
                  scheduler_job_id, dashboard_id, project_row_id, project_title,
                  execution_target, instructions, coding_workflow,
                  status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'queued', now())
                RETURNING id, tenant_id, created_by_user_id, execution_user_id, scheduler_job_id,
                          dashboard_id, project_row_id, project_title,
                          execution_target, instructions, coding_workflow, status, error,
                          started_at, finished_at, created_at, updated_at
                """,
                (
                    tenant_id,
                    created_by_user_id,
                    execution_user_id,
                    scheduler_job_id,
                    dashboard_id,
                    project_row_id,
                    project_title,
                    execution_target,
                    instructions,
                    Json(wf),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def fetch_queued_runs_coding(*, limit: int = 10) -> list[dict[str, Any]]:
    lim = max(1, min(50, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, scheduler_job_id,
                       dashboard_id, project_row_id, project_title,
                       execution_target, instructions, coding_workflow, status, error,
                       result_json, started_at, finished_at, created_at, updated_at
                FROM project_runs
                WHERE status = 'queued'
                  AND execution_target = 'coding'
                ORDER BY created_at ASC
                LIMIT %s
                """,
                (lim,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def get_run(*, run_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, scheduler_job_id,
                       dashboard_id, project_row_id, project_title,
                       execution_target, instructions, coding_workflow, status, error,
                       result_json, started_at, finished_at, created_at, updated_at
                FROM project_runs
                WHERE id = %s AND tenant_id = %s
                """,
                (run_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def list_runs(
    *,
    tenant_id: int,
    dashboard_id: uuid.UUID | None,
    project_row_id: str | None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    params: list[Any] = [tenant_id]
    where = "WHERE tenant_id = %s"
    if dashboard_id is not None:
        where += " AND dashboard_id = %s"
        params.append(dashboard_id)
    if project_row_id is not None and project_row_id.strip():
        where += " AND project_row_id = %s"
        params.append(project_row_id.strip())
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tenant_id, created_by_user_id, execution_user_id, scheduler_job_id,
                       dashboard_id, project_row_id, project_title,
                       execution_target, instructions, coding_workflow, status, error,
                       result_json, started_at, finished_at, created_at, updated_at
                FROM project_runs
                {}
                ORDER BY created_at DESC
                LIMIT %s
                """.format(where),
                params,
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def mark_running(*, run_id: uuid.UUID, tenant_id: int) -> bool:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_runs
                SET status = 'running', started_at = %s, updated_at = %s
                WHERE id = %s AND tenant_id = %s AND status = 'queued'
                """,
                (now, now, run_id, tenant_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def mark_done(
    *,
    run_id: uuid.UUID,
    tenant_id: int,
    status: RunStatus,
    error: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> bool:
    if status not in ("succeeded", "failed", "cancelled"):
        raise ValueError("invalid final status")
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_runs
                SET status = %s, error = %s, result_json = %s, finished_at = %s, updated_at = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (
                    status,
                    error,
                    Json(dict(result_json)) if result_json is not None else None,
                    now,
                    now,
                    run_id,
                    tenant_id,
                ),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out

