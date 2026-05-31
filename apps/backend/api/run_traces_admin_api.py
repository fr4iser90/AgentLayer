"""Admin API: persisted runs + correlated tool invocations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row

from apps.backend.infrastructure import agent_runs_store, agent_tasks_store
from apps.backend.infrastructure.auth import require_admin
from apps.backend.infrastructure.db import db

router = APIRouter(prefix="/v1/admin/run-traces", tags=["run-traces-admin"])


def _row_public(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


@router.get("/runs")
async def list_runs(
    request: Request,
    task_id: str | None = None,
    conversation_id: str | None = None,
    limit: int = 50,
) -> dict:
    admin = await require_admin(request)
    tid = db.user_tenant_id(admin.id)
    runs = agent_runs_store.list_runs(
        tenant_id=tid,
        task_id=uuid.UUID(task_id) if task_id else None,
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
        limit=limit,
    )
    return {"ok": True, "runs": [agent_runs_store.row_to_public(r) for r in runs]}


@router.get("/runs/{run_id}")
async def get_run_trace(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tenant_id = db.user_tenant_id(admin.id)
    run = agent_runs_store.get_run(run_id=run_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    tools: list[dict] = []
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
    child_runs = agent_runs_store.list_runs(
        tenant_id=tenant_id, parent_run_id=run_id, limit=50
    )
    task = None
    if run.get("task_id"):
        task = agent_tasks_store.get_task(
            task_id=uuid.UUID(str(run["task_id"])), tenant_id=tenant_id
        )
    return {
        "ok": True,
        "run": agent_runs_store.row_to_public(run),
        "task": agent_tasks_store.row_to_public(task) if task else None,
        "tool_invocations": [_row_public(t) for t in tools],
        "child_runs": [agent_runs_store.row_to_public(c) for c in child_runs],
    }


@router.get("/tool-invocations")
async def list_tool_invocations_admin(
    request: Request,
    run_id: str | None = None,
    limit: int = 100,
) -> dict:
    await require_admin(request)
    lim = max(1, min(500, int(limit)))
    where = "WHERE 1=1"
    params: list = []
    if run_id:
        try:
            rid = uuid.UUID(run_id.strip())
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail="invalid run_id") from e
        where += " AND agent_run_id = %s"
        params.append(rid)
    params.append(lim)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at,
                       tenant_id, user_id, agent_run_id
                FROM tool_invocations
                """ + where + """
                ORDER BY id DESC
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return {"ok": True, "invocations": [_row_public(r) for r in rows]}
