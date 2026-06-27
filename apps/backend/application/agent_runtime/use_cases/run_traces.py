from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.agent_runtime import agent_runs_store, agent_tasks_store
from apps.backend.infrastructure.db import db


def row_public(row: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def tenant_id_for_user(user_id: uuid.UUID) -> int:
    return db.user_tenant_id(user_id)


def list_agent_runs(
    *,
    tenant_id: int,
    task_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    parent_run_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return agent_runs_store.list_runs(
        tenant_id=tenant_id,
        task_id=task_id,
        conversation_id=conversation_id,
        parent_run_id=parent_run_id,
        limit=limit,
    )


def get_agent_run(*, run_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    return agent_runs_store.get_run(run_id=run_id, tenant_id=tenant_id)


def public_agent_run(row: dict[str, Any]) -> dict[str, Any]:
    return agent_runs_store.row_to_public(row)


def get_agent_task(*, task_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    return agent_tasks_store.get_task(task_id=task_id, tenant_id=tenant_id)


def public_agent_task(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return agent_tasks_store.row_to_public(row) if row else None


def list_tool_invocations(
    *,
    run_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    lim = max(1, min(500, int(limit)))
    where = "WHERE 1=1"
    params: list[Any] = []
    if run_id is not None:
        where += " AND agent_run_id = %s"
        params.append(run_id)
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at,
                       tenant_id, user_id, agent_run_id
                FROM tool_invocations
                """
                + where
                + """
                ORDER BY id DESC
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return rows


def tool_invocations_for_run(run_id: uuid.UUID) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at, agent_run_id
                FROM tool_invocations
                WHERE agent_run_id = %s
                ORDER BY id ASC
                LIMIT 500
                """,
                (run_id,),
            )
            tools = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return tools
