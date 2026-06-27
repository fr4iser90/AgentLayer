"""Persisted ``agent_runs`` (correlate chat/sub-agent/tool invocations)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

import logging

import psycopg

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


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


def insert_run_start(
    *,
    run_id: uuid.UUID,
    tenant_id: int,
    user_id: uuid.UUID,
    agent_id: str | None,
    task_id: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    embedded_subagent: bool = False,
) -> dict[str, Any]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO agent_runs (
                  id, tenant_id, user_id, task_id, parent_run_id,
                  conversation_id, workspace_id, agent_id, status,
                  embedded_subagent, started_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'running', %s, now())
                ON CONFLICT (id) DO NOTHING
                RETURNING *
                """,
                (
                    run_id,
                    tenant_id,
                    user_id,
                    task_id,
                    parent_run_id,
                    conversation_id,
                    workspace_id,
                    (agent_id or "").strip()[:128] or None,
                    embedded_subagent,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def run_exists(*, run_id: uuid.UUID, tenant_id: int) -> bool:
    return get_run(run_id=run_id, tenant_id=tenant_id) is not None


def insert_run_start_resilient(
    *,
    run_id: uuid.UUID,
    tenant_id: int,
    user_id: uuid.UUID,
    agent_id: str | None,
    task_id: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    embedded_subagent: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Insert ``agent_runs`` row; strip invalid FK refs and retry on failure."""
    from apps.backend.infrastructure.agent_runtime import agent_tasks_store

    warnings: list[str] = []
    tid = task_id
    if tid is not None and not agent_tasks_store.get_task(task_id=tid, tenant_id=tenant_id):
        warnings.append(
            f"active_task_id {tid} not found; agent run stored without task link"
        )
        tid = None

    prid = parent_run_id
    if prid is not None and not run_exists(run_id=prid, tenant_id=tenant_id):
        warnings.append(
            f"parent_run_id {prid} not found; agent run stored without parent link"
        )
        prid = None

    def _insert(t_id: uuid.UUID | None, p_id: uuid.UUID | None) -> dict[str, Any]:
        return insert_run_start(
            run_id=run_id,
            tenant_id=tenant_id,
            user_id=user_id,
            agent_id=agent_id,
            task_id=t_id,
            parent_run_id=p_id,
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            embedded_subagent=embedded_subagent,
        )

    try:
        row = _insert(tid, prid)
        if row:
            return row, warnings
        if run_exists(run_id=run_id, tenant_id=tenant_id):
            existing = get_run(run_id=run_id, tenant_id=tenant_id)
            return dict(existing or {}), warnings
    except psycopg.Error as exc:
        warnings.append(f"agent_runs insert failed ({exc}); retrying without task/parent links")
        logger.warning("agent_runs insert failed run_id=%s: %s", run_id, exc)

    try:
        row = _insert(None, None)
        if row:
            return row, warnings
        if run_exists(run_id=run_id, tenant_id=tenant_id):
            existing = get_run(run_id=run_id, tenant_id=tenant_id)
            return dict(existing or {}), warnings
    except psycopg.Error as exc:
        warnings.append(f"agent_runs insert failed permanently: {exc}")
        logger.warning("agent_runs insert permanently failed run_id=%s: %s", run_id, exc)
        return {}, warnings

    warnings.append("agent_runs insert returned no row")
    return {}, warnings


def count_running_for_user(user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int FROM agent_runs
                WHERE user_id = %s AND status = 'running' AND finished_at IS NULL
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _parse_run_uuid(raw: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError):
        return None


def running_workspace_ids_for_user(user_id: uuid.UUID) -> set[uuid.UUID]:
    """Workspaces tied to DB rows still marked running (includes stale zombies)."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT workspace_id FROM agent_runs
                WHERE user_id = %s AND status = 'running' AND finished_at IS NULL
                  AND workspace_id IS NOT NULL
                """,
                (user_id,),
            )
            rows = cur.fetchall()
    out: set[uuid.UUID] = set()
    for row in rows:
        wid = _parse_run_uuid(row[0])
        if wid is not None:
            out.add(wid)
    return out


def actively_running_workspace_ids_for_user(user_id: uuid.UUID) -> set[uuid.UUID]:
    """Workspaces with a live in-process agent worker (excludes Ctrl+C DB zombies)."""
    from apps.backend.domain.agent_runtime.run_cancel import registered_parent_run_ids

    live_ids = registered_parent_run_ids()
    if not live_ids:
        return set()
    live_uuids = {_parse_run_uuid(rid) for rid in live_ids}
    live_uuids.discard(None)
    if not live_uuids:
        return set()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT workspace_id FROM agent_runs
                WHERE user_id = %s AND status = 'running' AND finished_at IS NULL
                  AND workspace_id IS NOT NULL
                  AND id = ANY(%s)
                """,
                (user_id, list(live_uuids)),
            )
            rows = cur.fetchall()
    out: set[uuid.UUID] = set()
    for row in rows:
        wid = _parse_run_uuid(row[0])
        if wid is not None:
            out.add(wid)
    return out


_INTERRUPTED_AGENT_RUN_ERROR = (
    "Agent run interrupted: no live worker (server restart, Ctrl+C, or crash)."
)


def reconcile_orphaned_agent_runs(
    *,
    user_id: uuid.UUID | None = None,
    exclude_run_ids: set[uuid.UUID] | None = None,
) -> int:
    """Mark stale ``running`` agent_runs failed when no live worker holds them."""
    exclude = list(exclude_run_ids or ())
    where = ["status = 'running'", "finished_at IS NULL"]
    params: list[Any] = [_INTERRUPTED_AGENT_RUN_ERROR]
    if user_id is not None:
        where.append("user_id = %s")
        params.append(user_id)
    if exclude:
        where.append("NOT (id = ANY(%s::uuid[]))")
        params.append(exclude)
    sql = f"""
        UPDATE agent_runs
        SET status = 'failed',
            finished_at = COALESCE(finished_at, now()),
            error = COALESCE(NULLIF(TRIM(error), ''), %s)
        WHERE {' AND '.join(where)}
    """
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
            count = int(cur.rowcount or 0)
        conn.commit()
    return count


def reconcile_orphaned_agent_runs_on_startup() -> int:
    """After process start, no in-memory workers exist — clear all running rows."""
    return reconcile_orphaned_agent_runs()


def wait_for_user_runs_idle(
    user_id: uuid.UUID,
    *,
    timeout_sec: float = 180.0,
    poll_sec: float = 2.0,
) -> bool:
    """Block until no running agent_runs for user, or timeout. Returns True if idle."""
    import time

    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    while time.monotonic() < deadline:
        if count_running_for_user(user_id) <= 0:
            return True
        time.sleep(max(0.25, float(poll_sec)))
    return count_running_for_user(user_id) <= 0


def finish_run(
    *,
    run_id: uuid.UUID,
    status: str,
    token_usage: dict[str, Any] | None = None,
    error: str | None = None,
) -> bool:
    if status not in ("succeeded", "failed", "cancelled"):
        raise ValueError("invalid finish status")
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_runs
                SET status = %s, finished_at = %s, token_usage = %s, error = %s
                WHERE id = %s
                """,
                (
                    status,
                    now,
                    Json(dict(token_usage or {})),
                    (error or "")[:4000] or None,
                    run_id,
                ),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def get_run(*, run_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM agent_runs WHERE id = %s AND tenant_id = %s",
                (run_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def list_runs(
    *,
    tenant_id: int,
    user_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    where = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if user_id is not None:
        where.append("user_id = %s")
        params.append(user_id)
    if task_id is not None:
        where.append("task_id = %s")
        params.append(task_id)
    if conversation_id is not None:
        where.append("conversation_id = %s")
        params.append(conversation_id)
    if parent_run_id is not None:
        where.append("parent_run_id = %s")
        params.append(parent_run_id)
    params.append(lim)
    # SECURITY: WHERE conditions come from function parameters with fixed column names.
    # All values are parameterized via %s placeholders.
    sql = """
        SELECT * FROM agent_runs
        WHERE {}
        ORDER BY started_at DESC
        LIMIT %s
    """.format(' AND '.join(where))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]
