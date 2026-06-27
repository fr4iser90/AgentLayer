"""HTTP API for ``scheduler_job_runs`` (coding schedule execution history)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from apps.backend.application.identity.use_cases.request_auth import get_current_user, require_admin
from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.scheduling.use_cases.scheduling_controller_services import scheduler_job_runs_store

user_router = APIRouter(prefix="/v1/user", tags=["scheduler-job-runs-user"])
admin_router = APIRouter(prefix="/v1/admin", tags=["scheduler-job-runs-admin"])


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid job_id") from e


def _parse_run_id(run_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(run_id.strip())
    except (ValueError, AttributeError) as e:
        raise HTTPException(status_code=400, detail="invalid run_id") from e


@user_router.get("/scheduler-jobs/{job_id}/runs")
async def user_list_scheduler_job_runs(
    request: Request, job_id: str, limit: int = 20
) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    jid = _parse_job_id(job_id)
    if not scheduler_job_runs_store.user_can_view_job(
        job_id=jid,
        tenant_id=tenant_id,
        user_id=user.id,
        is_admin=(user.role == "admin"),
    ):
        raise HTTPException(status_code=404, detail="job not found or not allowed")
    rows = scheduler_job_runs_store.list_runs_for_job(
        scheduler_job_id=jid, tenant_id=tenant_id, limit=limit
    )
    return {"ok": True, "runs": [scheduler_job_runs_store.row_to_public(r) for r in rows]}


@user_router.get("/scheduler-job-runs/{run_id}")
async def user_get_scheduler_job_run(request: Request, run_id: str) -> dict:
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    rid = _parse_run_id(run_id)
    row = scheduler_job_runs_store.get_run(run_id=rid, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    jid = row.get("scheduler_job_id")
    if not isinstance(jid, uuid.UUID):
        try:
            jid = uuid.UUID(str(jid))
        except (ValueError, TypeError) as e:
            raise HTTPException(status_code=500, detail="invalid run row") from e
    if not scheduler_job_runs_store.user_can_view_job(
        job_id=jid,
        tenant_id=tenant_id,
        user_id=user.id,
        is_admin=(user.role == "admin"),
    ):
        raise HTTPException(status_code=404, detail="run not found or not allowed")
    return {"ok": True, "run": scheduler_job_runs_store.row_to_public(row)}


@admin_router.get("/scheduler-jobs/{job_id}/runs")
async def admin_list_scheduler_job_runs(
    request: Request, job_id: str, limit: int = 20
) -> dict:
    await require_admin(request)
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    jid = _parse_job_id(job_id)
    rows = scheduler_job_runs_store.list_runs_for_job(
        scheduler_job_id=jid, tenant_id=tenant_id, limit=limit
    )
    return {"ok": True, "runs": [scheduler_job_runs_store.row_to_public(r) for r in rows]}


@admin_router.get("/scheduler-job-runs/{run_id}")
async def admin_get_scheduler_job_run(request: Request, run_id: str) -> dict:
    await require_admin(request)
    user = await get_current_user(request)
    tenant_id = db.user_tenant_id(user.id)
    rid = _parse_run_id(run_id)
    row = scheduler_job_runs_store.get_run(run_id=rid, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return {"ok": True, "run": scheduler_job_runs_store.row_to_public(row)}
