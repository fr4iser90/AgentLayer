"""User HTTP API for persisted `scheduler_jobs` (user-defined schedules)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import normalize_coding_workflow
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import scheduler_jobs_store
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import dashboard_access_ex
from apps.backend.domain.scheduling.targets import (
    agent_requires_workspace_for_target,
    execution_target_error,
    is_valid_execution_target,
    normalize_execution_target,
    schedule_permission_error,
)

router = APIRouter(prefix="/v1/user/scheduler-jobs", tags=["scheduler-jobs-user"])


class SchedulerJobCreateBody(BaseModel):
    execution_target: str = Field(..., max_length=32)
    interval_minutes: int = Field(default=60, ge=5, le=10080)
    enabled: bool = True
    title: str | None = Field(default=None, max_length=500)
    instructions: str = Field(..., min_length=1, max_length=32000)
    dashboard_id: str | None = None
    coding_workflow: dict[str, Any] | None = None
    workspace_id: str | None = Field(
        default=None,
        description="Required for workspace agents unless in coding_workflow",
    )


class SchedulerJobSetEnabledBody(BaseModel):
    enabled: bool = Field(...)


class SchedulerJobPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=32000)
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)


@router.get("/execution-targets")
async def scheduler_execution_targets_catalog(request: Request) -> dict[str, Any]:
    """Scheduled job modes (not the full agent registry — only targets with a cron runner)."""
    await get_current_user(request)
    from apps.backend.domain.scheduling.targets import execution_target_catalog

    return {"ok": True, "targets": execution_target_catalog()}


@router.get("")
async def scheduler_job_list(request: Request, dashboard_id: str | None = None, limit: int = 50) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    ws_id: uuid.UUID | None = None
    if dashboard_id is not None and str(dashboard_id).strip():
        try:
            ws_id = uuid.UUID(str(dashboard_id).strip())
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail="invalid dashboard_id") from e
    rows = scheduler_jobs_store.list_jobs_for_user(
        tenant_id=tenant_id,
        current_user_id=user.id,
        is_admin=(user.role == "admin"),
        dashboard_id=ws_id,
        limit=limit,
    )
    return {"ok": True, "jobs": [scheduler_jobs_store.row_to_public(r) for r in rows]}


@router.post("")
async def scheduler_job_create(request: Request, body: SchedulerJobCreateBody) -> dict[str, Any]:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    tgt = normalize_execution_target(body.execution_target)
    if not tgt or not is_valid_execution_target(tgt):
        raise HTTPException(status_code=400, detail=execution_target_error(body.execution_target))
    perm_err = schedule_permission_error(user_role=user.role, execution_target=tgt or "")
    if perm_err:
        if "requires admin" in perm_err:
            raise HTTPException(status_code=403, detail=perm_err)
        raise HTTPException(status_code=400, detail=perm_err)

    ws_id: uuid.UUID | None = None
    if body.dashboard_id is not None and str(body.dashboard_id).strip():
        try:
            ws_id = uuid.UUID(str(body.dashboard_id).strip())
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=400, detail="invalid dashboard_id") from e
        d = dashboard_access_ex(user.id, tenant_id, ws_id)
        if d.role is None:
            raise HTTPException(status_code=403, detail="dashboard not accessible")
        if d.allowed_block_ids is None:
            if d.role not in ("owner", "co_owner", "editor"):
                raise HTTPException(status_code=403, detail="dashboard is read-only for this user")
        else:
            if not d.granular_can_write:
                raise HTTPException(status_code=403, detail="dashboard is read-only for this user")

    wf_raw: dict[str, Any] = dict(body.coding_workflow or {})
    if body.workspace_id and str(body.workspace_id).strip():
        wf_raw.setdefault("workspace_id", str(body.workspace_id).strip())
    try:
        wf = normalize_coding_workflow(
            wf_raw, require_workspace=agent_requires_workspace_for_target(tgt)
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    row = scheduler_jobs_store.insert_job(
        tenant_id=tenant_id,
        created_by_user_id=user.id,
        execution_user_id=user.id,
        dashboard_id=ws_id,
        execution_target=tgt,
        title=(body.title or "").strip() or None,
        instructions=body.instructions.strip(),
        interval_minutes=int(body.interval_minutes),
        enabled=bool(body.enabled),
        coding_workflow=wf,
    )
    if not row:
        raise HTTPException(status_code=500, detail="failed to create job")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}


@router.patch("/{job_id}")
async def scheduler_job_patch(request: Request, job_id: str, body: SchedulerJobPatchBody) -> dict[str, Any]:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    try:
        jid = uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid job_id") from e
    row = scheduler_jobs_store.update_job(
        job_id=jid,
        tenant_id=tenant_id,
        actor_user_id=user.id,
        actor_is_admin=(user.role == "admin"),
        title=body.title.strip() if isinstance(body.title, str) else None,
        instructions=body.instructions.strip() if isinstance(body.instructions, str) else None,
        interval_minutes=body.interval_minutes,
        coding_workflow=None,
    )
    if not row:
        raise HTTPException(status_code=404, detail="job not found or not allowed")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}


@router.delete("/{job_id}")
async def scheduler_job_hard_delete(request: Request, job_id: str) -> dict[str, Any]:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    try:
        jid = uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid job_id") from e
    ok = scheduler_jobs_store.hard_delete_job(
        job_id=jid,
        tenant_id=tenant_id,
        actor_user_id=user.id,
        actor_is_admin=(user.role == "admin"),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="job not found or not allowed")
    return {"ok": True, "deleted": True, "job_id": str(jid)}


@router.patch("/{job_id}/enabled")
async def scheduler_job_set_enabled(
    request: Request, job_id: str, body: SchedulerJobSetEnabledBody
) -> dict[str, Any]:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    try:
        jid = uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid job_id") from e
    row = scheduler_jobs_store.set_enabled(
        job_id=jid,
        tenant_id=tenant_id,
        enabled=bool(body.enabled),
        actor_user_id=user.id,
        actor_is_admin=(user.role == "admin"),
    )
    if not row:
        raise HTTPException(status_code=404, detail="job not found or not allowed")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}
