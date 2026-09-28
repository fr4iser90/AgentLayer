"""Admin HTTP API for persisted `scheduler_jobs` (user-defined schedules).

The company-wide half of the same table the user API serves, so it answers two
questions the user half never has to: how far may this caller see
(:meth:`AdminScope.tenant_filter`) and whose job is this
(:meth:`AdminScope.require_tenant`). Before both were answered by
``db.user_tenant_id(actor)`` a site admin saw only their own company's schedules
while a delegated holder could target agents their company's allowlist denies —
too narrow in one direction, too wide in the other.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.identity.use_cases.request_auth import (
    agent_effective_role,
    require_admin_scope,
)
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import normalize_coding_workflow
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.domain.access.capabilities import AdminScopeError, CAP_SCHEDULE_MANAGE
from apps.backend.domain.scheduling.targets import (
    agent_requires_workspace_for_target,
    execution_target_error,
    is_valid_execution_target,
    normalize_execution_target,
    schedule_permission_error,
)
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import scheduler_jobs_store

router = APIRouter(prefix="/v1/admin/scheduler-jobs", tags=["scheduler-jobs-admin"])


class SchedulerJobSetEnabledBody(BaseModel):
    enabled: bool = Field(...)


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
    tenant_id: int | None = Field(
        default=None,
        description="Company to create in. A delegated holder may only name their own.",
    )


class SchedulerJobPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    instructions: str | None = Field(default=None, max_length=32000)
    interval_minutes: int | None = Field(default=None, ge=5, le=10080)
    coding_workflow: dict[str, Any] | None = None
    workspace_id: str | None = None


class SchedulerJobArchiveBody(BaseModel):
    archived: bool = Field(...)


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid job_id") from e


def _parse_dashboard_id(dashboard_id: str | None) -> uuid.UUID | None:
    if dashboard_id is None or not str(dashboard_id).strip():
        return None
    try:
        return uuid.UUID(str(dashboard_id).strip())
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail="invalid dashboard_id") from e


def _narrow_tenant(scope: Any, tenant_id: int | None) -> int:
    """An explicit company filter, kept inside the caller's range.

    Denied rather than ignored: a caller who names a company they cannot reach is
    asking for something they were not granted, and silently getting their own
    company instead would report a filtered list that is not the one requested.
    """
    if tenant_id is None:
        return int(db.user_tenant_id(scope.actor_id) or 1)
    try:
        return scope.require_tenant(tenant_id, what="tenant")
    except AdminScopeError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e


def _job_tenant(scope: Any, jid: uuid.UUID) -> int:
    """The company a job belongs to, when the caller reaches it.

    Answers 404 outside the scope, not 403 — confirming that another company has
    a job with this id is itself a leak.
    """
    row = scheduler_jobs_store.get_job_any_tenant(jid)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    try:
        return scope.require_tenant(row.get("tenant_id"), what="job")
    except AdminScopeError as e:
        raise HTTPException(status_code=404, detail="job not found") from e


def _merge_coding_workflow(
    body_wf: dict[str, Any] | None,
    workspace_id: str | None,
    *,
    execution_target: str,
) -> dict[str, Any]:
    wf_raw: dict[str, Any] = dict(body_wf or {})
    if workspace_id and str(workspace_id).strip():
        wf_raw.setdefault("workspace_id", str(workspace_id).strip())
    require_ws = agent_requires_workspace_for_target(execution_target)
    try:
        return normalize_coding_workflow(wf_raw, require_workspace=require_ws)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("")
async def scheduler_job_list(
    request: Request,
    dashboard_id: str | None = None,
    include_global: bool = False,
    include_archived: bool = False,
    execution_target: str | None = None,
    enabled: bool | None = None,
    tenant_id: int | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    ws_id = _parse_dashboard_id(dashboard_id)
    tgt = normalize_execution_target(execution_target) if execution_target else None
    if tgt is not None and not is_valid_execution_target(tgt):
        raise HTTPException(status_code=400, detail=execution_target_error(tgt))
    tenant_ids: frozenset[int] | None = scope.tenant_filter()
    if tenant_id is not None:
        tenant_ids = frozenset({_narrow_tenant(scope, tenant_id)})
    rows = scheduler_jobs_store.list_jobs_for_scope(
        tenant_ids=tenant_ids,
        dashboard_id=ws_id,
        include_global=bool(include_global),
        execution_target=tgt,
        enabled=enabled,
        include_archived=bool(include_archived),
        limit=limit,
    )
    return {"ok": True, "jobs": [scheduler_jobs_store.row_to_public(r) for r in rows]}


@router.post("")
async def scheduler_job_create(request: Request, body: SchedulerJobCreateBody) -> dict[str, Any]:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    tenant_id = _narrow_tenant(scope, body.tenant_id)
    tgt = normalize_execution_target(body.execution_target)
    if not tgt or not is_valid_execution_target(tgt):
        raise HTTPException(status_code=400, detail=execution_target_error(body.execution_target))
    # The same two-layer target policy the user path applies. Skipping it here is
    # how a delegated holder could schedule an agent their company's allowlist
    # denies — the capability says what, never which agent.
    perm_err = schedule_permission_error(
        user_role=agent_effective_role(scope.actor_id),
        execution_target=tgt,
        user_id=scope.actor_id,
        tenant_id=tenant_id,
    )
    if perm_err:
        raise HTTPException(status_code=403, detail=perm_err)
    ws_id = _parse_dashboard_id(body.dashboard_id)
    try:
        wf = _merge_coding_workflow(
            body.coding_workflow, body.workspace_id, execution_target=tgt
        )
        row = scheduler_jobs_store.insert_job(
            tenant_id=tenant_id,
            created_by_user_id=scope.actor_id,
            execution_user_id=scope.actor_id,
            dashboard_id=ws_id,
            execution_target=tgt,
            title=(body.title or "").strip() or None,
            instructions=body.instructions.strip(),
            interval_minutes=int(body.interval_minutes),
            enabled=bool(body.enabled),
            coding_workflow=wf,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not row:
        raise HTTPException(status_code=500, detail="failed to create job")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}


@router.patch("/{job_id}")
async def scheduler_job_patch(request: Request, job_id: str, body: SchedulerJobPatchBody) -> dict[str, Any]:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    jid = _parse_job_id(job_id)
    tenant_id = _job_tenant(scope, jid)
    wf: dict[str, Any] | None = None
    if body.coding_workflow is not None or body.workspace_id is not None:
        existing = scheduler_jobs_store.get_job(jid, tenant_id) or {}
        tgt = str(existing.get("execution_target") or "").strip().lower()
        merged = dict(existing.get("coding_workflow") or {})
        if isinstance(body.coding_workflow, dict):
            merged.update(body.coding_workflow)
        try:
            wf = _merge_coding_workflow(
                merged,
                body.workspace_id,
                execution_target=normalize_execution_target(tgt) or tgt or "coding",
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        row = scheduler_jobs_store.update_job(
            job_id=jid,
            tenant_id=tenant_id,
            actor_user_id=scope.actor_id,
            actor_is_admin=True,
            title=body.title.strip() if isinstance(body.title, str) else None,
            instructions=body.instructions.strip() if isinstance(body.instructions, str) else None,
            interval_minutes=body.interval_minutes,
            coding_workflow=wf,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}


@router.patch("/{job_id}/archived")
async def scheduler_job_set_archived(
    request: Request, job_id: str, body: SchedulerJobArchiveBody
) -> dict[str, Any]:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    jid = _parse_job_id(job_id)
    tenant_id = _job_tenant(scope, jid)
    if body.archived:
        ok = scheduler_jobs_store.archive_job(
            job_id=jid, tenant_id=tenant_id, actor_user_id=scope.actor_id, actor_is_admin=True
        )
    else:
        ok = scheduler_jobs_store.unarchive_job(
            job_id=jid, tenant_id=tenant_id, actor_user_id=scope.actor_id, actor_is_admin=True
        )
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    row = scheduler_jobs_store.get_job(jid, tenant_id)
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row or {})}


@router.delete("/{job_id}")
async def scheduler_job_hard_delete(request: Request, job_id: str) -> dict[str, Any]:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    jid = _parse_job_id(job_id)
    tenant_id = _job_tenant(scope, jid)
    ok = scheduler_jobs_store.hard_delete_job(
        job_id=jid, tenant_id=tenant_id, actor_user_id=scope.actor_id, actor_is_admin=True
    )
    if not ok:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "deleted": True, "job_id": str(jid)}


@router.patch("/{job_id}/enabled")
async def scheduler_job_set_enabled(request: Request, job_id: str, body: SchedulerJobSetEnabledBody) -> dict:
    scope = await require_admin_scope(request, CAP_SCHEDULE_MANAGE)
    jid = _parse_job_id(job_id)
    tenant_id = _job_tenant(scope, jid)
    row = scheduler_jobs_store.set_enabled(
        job_id=jid,
        tenant_id=tenant_id,
        enabled=bool(body.enabled),
        actor_user_id=scope.actor_id,
        actor_is_admin=True,
    )
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": scheduler_jobs_store.row_to_public(row)}
