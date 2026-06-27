"""Admin API: persisted runs + correlated tool invocations."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.agent_runtime.use_cases.run_traces import (
    get_agent_run,
    get_agent_task,
    list_agent_runs,
    list_tool_invocations,
    public_agent_run,
    public_agent_task,
    row_public,
    tenant_id_for_user,
    tool_invocations_for_run,
)
from apps.backend.application.identity.use_cases.request_auth import require_admin

router = APIRouter(prefix="/v1/admin/run-traces", tags=["run-traces-admin"])


def _row_public(row: dict) -> dict:
    return row_public(row)


@router.get("/runs")
async def list_runs(
    request: Request,
    task_id: str | None = None,
    conversation_id: str | None = None,
    limit: int = 50,
) -> dict:
    admin = await require_admin(request)
    tid = tenant_id_for_user(admin.id)
    runs = list_agent_runs(
        tenant_id=tid,
        task_id=uuid.UUID(task_id) if task_id else None,
        conversation_id=uuid.UUID(conversation_id) if conversation_id else None,
        limit=limit,
    )
    return {"ok": True, "runs": [public_agent_run(r) for r in runs]}


@router.get("/runs/{run_id}")
async def get_run_trace(request: Request, run_id: uuid.UUID) -> dict:
    admin = await require_admin(request)
    tenant_id = tenant_id_for_user(admin.id)
    run = get_agent_run(run_id=run_id, tenant_id=tenant_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    tools = tool_invocations_for_run(run_id)
    child_runs = list_agent_runs(
        tenant_id=tenant_id, parent_run_id=run_id, limit=50
    )
    task = None
    if run.get("task_id"):
        task = get_agent_task(
            task_id=uuid.UUID(str(run["task_id"])), tenant_id=tenant_id
        )
    return {
        "ok": True,
        "run": public_agent_run(run),
        "task": public_agent_task(task),
        "tool_invocations": [_row_public(t) for t in tools],
        "child_runs": [public_agent_run(c) for c in child_runs],
    }


@router.get("/tool-invocations")
async def list_tool_invocations_admin(
    request: Request,
    run_id: str | None = None,
    limit: int = 100,
) -> dict:
    await require_admin(request)
    rid = None
    if run_id:
        try:
            rid = uuid.UUID(run_id.strip())
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail="invalid run_id") from e
    rows = list_tool_invocations(run_id=rid, limit=limit)
    return {"ok": True, "invocations": [_row_public(r) for r in rows]}
