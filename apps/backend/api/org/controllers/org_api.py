"""Organization-scoped HTTP (tenant admin, multi_tenant mode)."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.org.use_cases import org_controller_services as org_svc
from apps.backend.application.rag.use_cases import rag_controller_services as rag_ctrl
from apps.backend.application.identity.use_cases.request_auth import require_tenant_admin

logger = logging.getLogger(__name__)

db = org_svc.db
http_500_detail = org_svc.http_500_detail
op_settings = org_svc.operator_settings

router = APIRouter()


class OrgTenantPatchBody(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    vertical_profile: str | None = Field(default=None, max_length=64)


class OrgSetupCompleteBody(BaseModel):
    disclaimer_accepted: bool = False
    start_empty: bool = False
    published_note: bool = False


class OrgRagIngestBody(BaseModel):
    text: str = Field(min_length=1)
    title: str = Field(default="", max_length=512)
    source_uri: str | None = Field(default=None, max_length=1024)


def _tenant_id_for(user: Any) -> int:
    return db.user_tenant_id(user.id)


@router.get("/v1/org/tenant")
async def org_get_tenant(request: Request):
    user = await require_tenant_admin(request)
    tid = _tenant_id_for(user)
    row = db.tenant_get(tid)
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return {
        "tenant": row,
        "membership_role": db.user_membership_role(user.id, tid),
        "deployment_mode": op_settings.deployment_mode(),
        "setup_required": row.get("setup_completed_at") is None,
    }


@router.patch("/v1/org/tenant")
async def org_patch_tenant(request: Request, body: OrgTenantPatchBody):
    user = await require_tenant_admin(request)
    tid = _tenant_id_for(user)
    row = db.tenant_update_org_profile(
        tid,
        name=body.name,
        vertical_profile=body.vertical_profile,
    )
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return {"tenant": row}


@router.post("/v1/org/setup/complete")
async def org_setup_complete(request: Request, body: OrgSetupCompleteBody = Body(...)):
    user = await require_tenant_admin(request)
    if not body.disclaimer_accepted:
        raise HTTPException(status_code=400, detail="disclaimer must be accepted")
    if not body.start_empty and not body.published_note:
        raise HTTPException(
            status_code=400,
            detail="publish a note or confirm empty knowledge base",
        )
    tid = _tenant_id_for(user)
    row = db.tenant_mark_setup_completed(tid)
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return {"ok": True, "tenant": row}


@router.post("/v1/org/rag/ingest")
async def org_rag_ingest(request: Request, body: OrgRagIngestBody):
    user = await require_tenant_admin(request)
    if op_settings.deployment_mode() != "multi_tenant":
        raise HTTPException(status_code=404, detail="not available in agent_system mode")
    if not rag_ctrl.operator_settings.rag_settings()["enabled"]:
        raise HTTPException(status_code=503, detail="RAG disabled (operator settings)")
    tid = _tenant_id_for(user)
    tenant_row = db.tenant_get(tid)
    if tenant_row and tenant_row.get("setup_completed_at") is None:
        raise HTTPException(status_code=403, detail="complete organization setup first")
    domain = "tenant_knowledge"
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    title = (body.title or "").strip()
    su = (body.source_uri or "").strip() or None
    try:
        out = rag_ctrl.rag_service.ingest_for_user(tid, user.id, domain, title, text, su)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        logger.exception("org RAG ingest embedding HTTP error")
        detail = (
            f"Embedding HTTP error: {e!s}"
            if rag_ctrl.operator_settings.expose_internal_errors_in_responses()
            else "Embedding HTTP error"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except httpx.RequestError as e:
        logger.exception("org RAG ingest cannot reach embedding backend")
        detail = (
            f"Embedding backend unreachable: {e!s}"
            if rag_ctrl.operator_settings.expose_internal_errors_in_responses()
            else "Embedding backend unreachable"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except Exception as e:
        logger.exception("org RAG ingest failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    return out
