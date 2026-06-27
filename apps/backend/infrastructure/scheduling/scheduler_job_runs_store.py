"""CRUD for ``scheduler_job_runs`` (execution history for coding schedules)."""

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


def insert_run_start(
    *,
    scheduler_job_id: uuid.UUID,
    tenant_id: int,
    execution_user_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    agent_id: str | None,
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO scheduler_job_runs (
                  scheduler_job_id, tenant_id, execution_user_id, workspace_id,
                  agent_id, status, summary_json, started_at
                )
                VALUES (%s, %s, %s, %s, %s, 'running', '{}'::jsonb, now())
                RETURNING id, scheduler_job_id, tenant_id, execution_user_id, workspace_id,
                          agent_id, status, error, summary_json, started_at, finished_at, created_at
                """,
                (
                    scheduler_job_id,
                    tenant_id,
                    execution_user_id,
                    workspace_id,
                    agent_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def finish_run(
    *,
    run_id: uuid.UUID,
    tenant_id: int,
    status: str,
    error: str | None,
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE scheduler_job_runs
                SET status = %s,
                    error = %s,
                    summary_json = %s,
                    finished_at = %s
                WHERE id = %s AND tenant_id = %s
                RETURNING id, scheduler_job_id, tenant_id, execution_user_id, workspace_id,
                          agent_id, status, error, summary_json, started_at, finished_at, created_at
                """,
                (status, error, Json(summary), now, run_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def list_runs_for_job(
    *,
    scheduler_job_id: uuid.UUID,
    tenant_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    lim = max(1, min(100, limit))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, scheduler_job_id, tenant_id, execution_user_id, workspace_id,
                       agent_id, status, error, summary_json, started_at, finished_at, created_at
                FROM scheduler_job_runs
                WHERE scheduler_job_id = %s AND tenant_id = %s
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (scheduler_job_id, tenant_id, lim),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def get_run(*, run_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, scheduler_job_id, tenant_id, execution_user_id, workspace_id,
                       agent_id, status, error, summary_json, started_at, finished_at, created_at
                FROM scheduler_job_runs
                WHERE id = %s AND tenant_id = %s
                """,
                (run_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def user_can_view_job(
    *,
    job_id: uuid.UUID,
    tenant_id: int,
    user_id: uuid.UUID,
    is_admin: bool,
) -> bool:
    from apps.backend.infrastructure.scheduling import scheduler_jobs_store

    row = scheduler_jobs_store.get_job(job_id, tenant_id)
    if not row:
        return False
    if is_admin:
        return True
    cb = row.get("created_by_user_id")
    ex = row.get("execution_user_id")
    return cb == user_id or ex == user_id


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
