"""Tenant CMS HTTP — org admin, site admin, and runtime read."""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from apps.backend.application.tenant_content.use_cases import tenant_content_controller_services as cms_ctrl
from apps.backend.application.identity.use_cases.request_auth import (
    require_site_admin,
    require_tenant_admin,
    require_tenant_member,
)

cms = cms_ctrl.cms
CAP_CONTENT_EDITOR = cms_ctrl.CAP_CONTENT_EDITOR
CAP_CONTENT_REVIEW = cms_ctrl.CAP_CONTENT_REVIEW
content_visible_to_policy = cms_ctrl.content_visible_to_policy
effective_policy = cms_ctrl.effective_policy
require_capability = cms_ctrl.require_capability
db = cms_ctrl.db
get_current_user = cms_ctrl.get_current_user
http_500_detail = cms_ctrl.http_500_detail
operator_settings = cms_ctrl.operator_settings

logger = __import__("logging").getLogger(__name__)

router = APIRouter()
org_router = APIRouter()
admin_router = APIRouter()


class TenantContentCreateBody(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body_md: str = Field(min_length=1)
    slug: str | None = Field(default=None, max_length=128)
    disclaimer_level: str | None = Field(default=None, max_length=32)
    vertical_profile: str | None = Field(default=None, max_length=64)
    source_type: str | None = Field(default=None, max_length=32)
    target_profession_roles: list[str] = Field(default_factory=list)
    target_departments: list[str] = Field(default_factory=list)
    required_qualifications: list[str] = Field(default_factory=list)
    content_category: str | None = Field(default=None, max_length=64)


class TenantContentRejectBody(BaseModel):
    comment: str = Field(min_length=1, max_length=4000)


class TenantContentPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=512)
    body_md: str | None = Field(default=None, min_length=1)
    slug: str | None = Field(default=None, max_length=128)
    disclaimer_level: str | None = Field(default=None, max_length=32)
    vertical_profile: str | None = Field(default=None, max_length=64)
    target_profession_roles: list[str] | None = None
    target_departments: list[str] | None = None
    required_qualifications: list[str] | None = None
    content_category: str | None = Field(default=None, max_length=64)


def _tenant_id_for(user: Any) -> int:
    return db.user_tenant_id(user.id)


def _parse_content_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid content id") from exc


def _publish_or_http_error(**kwargs: Any) -> dict[str, Any]:
    if not operator_settings.rag_settings()["enabled"]:
        raise HTTPException(status_code=503, detail="RAG disabled (operator settings)")
    try:
        return cms.publish_content(**kwargs)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except httpx.HTTPStatusError as e:
        logger.exception("tenant content publish embedding HTTP error")
        detail = (
            f"Embedding HTTP error: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding HTTP error"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except httpx.RequestError as e:
        logger.exception("tenant content publish cannot reach embedding backend")
        detail = (
            f"Embedding backend unreachable: {e!s}"
            if operator_settings.expose_internal_errors_in_responses()
            else "Embedding backend unreachable"
        )
        raise HTTPException(status_code=502, detail=detail) from e
    except Exception as e:
        logger.exception("tenant content publish failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e


@org_router.get("/v1/org/tenant-content")
async def org_list_tenant_content(
    request: Request,
    status: str | None = Query(default=None),
):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    policy = effective_policy(user.id, tid)
    require_capability(policy, CAP_CONTENT_EDITOR)
    rows = db.tenant_content_list(tid, status=status)
    return {"items": rows}


@org_router.post("/v1/org/tenant-content")
async def org_create_tenant_content(request: Request, body: TenantContentCreateBody):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    row = cms.create_draft(
        tenant_id=tid,
        user_id=user.id,
        title=body.title,
        body_md=body.body_md,
        slug=body.slug,
        disclaimer_level=body.disclaimer_level,
        vertical_profile=body.vertical_profile,
        source_type=body.source_type,
        target_profession_roles=body.target_profession_roles,
        target_departments=body.target_departments,
        required_qualifications=body.required_qualifications,
        content_category=body.content_category,
    )
    return {"content": row}


@org_router.get("/v1/org/tenant-content/review-queue")
async def org_review_queue(request: Request):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    policy = effective_policy(user.id, tid)
    require_capability(policy, CAP_CONTENT_REVIEW)
    rows = db.tenant_content_list(tid, status="in_review")
    return {"items": rows}


@org_router.get("/v1/org/tenant-content/{content_id}")
async def org_get_tenant_content(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    policy = effective_policy(user.id, tid)
    require_capability(policy, CAP_CONTENT_EDITOR)
    cid = _parse_content_id(content_id)
    row = db.tenant_content_get(cid, tid)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    return {"content": row}


@org_router.patch("/v1/org/tenant-content/{content_id}")
async def org_patch_tenant_content(
    request: Request,
    content_id: str,
    body: TenantContentPatchBody,
):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    policy = effective_policy(user.id, tid)
    require_capability(policy, CAP_CONTENT_EDITOR)
    cid = _parse_content_id(content_id)
    row = cms.update_content(
        tenant_id=tid,
        content_id=cid,
        user_id=user.id,
        title=body.title,
        body_md=body.body_md,
        slug=body.slug,
        disclaimer_level=body.disclaimer_level,
        vertical_profile=body.vertical_profile,
        target_profession_roles=body.target_profession_roles,
        target_departments=body.target_departments,
        required_qualifications=body.required_qualifications,
        content_category=body.content_category,
    )
    return {"content": row}


@org_router.post("/v1/org/tenant-content/{content_id}/publish")
async def org_publish_tenant_content(
    request: Request,
    content_id: str,
    override: bool = Query(default=False),
):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return _publish_or_http_error(tenant_id=tid, user_id=user.id, content_id=cid, override=override)


@org_router.post("/v1/org/tenant-content/{content_id}/submit-for-review")
async def org_submit_for_review(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return cms.submit_for_review(tenant_id=tid, user_id=user.id, content_id=cid)


@org_router.post("/v1/org/tenant-content/{content_id}/approve")
async def org_approve_content(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    policy = effective_policy(user.id, tid)
    require_capability(policy, CAP_CONTENT_REVIEW)
    cid = _parse_content_id(content_id)
    row = cms.approve_content(tenant_id=tid, user_id=user.id, content_id=cid)
    return {"content": row}


@org_router.post("/v1/org/tenant-content/{content_id}/reject")
async def org_reject_content(request: Request, content_id: str, body: TenantContentRejectBody):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.reject_content(tenant_id=tid, user_id=user.id, content_id=cid, comment=body.comment)
    return {"content": row}


@org_router.get("/v1/org/tenant-content/{content_id}/versions")
async def org_list_versions(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    items = cms.list_versions(tenant_id=tid, content_id=cid, user_id=user.id)
    return {"items": items}


@org_router.get("/v1/org/tenant-content/{content_id}/versions/diff")
async def org_version_diff(
    request: Request,
    content_id: str,
    from_version: int = Query(..., ge=1),
    to_version: int = Query(..., ge=1),
):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return cms.version_diff(
        tenant_id=tid,
        content_id=cid,
        user_id=user.id,
        from_version=from_version,
        to_version=to_version,
    )


@org_router.get("/v1/org/tenant-content/{content_id}/audit")
async def org_content_audit(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    items = cms.list_audit_events(tenant_id=tid, content_id=cid, user_id=user.id)
    return {"items": items}


@org_router.post("/v1/org/tenant-content/{content_id}/archive")
async def org_archive_tenant_content(request: Request, content_id: str):
    user = await require_tenant_member(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.archive_content(tenant_id=tid, user_id=user.id, content_id=cid)
    return {"content": row}


@admin_router.get("/v1/admin/tenant-content")
async def admin_list_tenant_content(
    request: Request,
    status: str | None = Query(default=None),
):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    rows = db.tenant_content_list(tid, status=status)
    return {"items": rows}


@admin_router.post("/v1/admin/tenant-content")
async def admin_create_tenant_content(request: Request, body: TenantContentCreateBody):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    row = cms.create_draft(
        tenant_id=tid,
        user_id=user.id,
        title=body.title,
        body_md=body.body_md,
        slug=body.slug,
        disclaimer_level=body.disclaimer_level,
        vertical_profile=body.vertical_profile,
        source_type=body.source_type,
        target_profession_roles=body.target_profession_roles,
        target_departments=body.target_departments,
        required_qualifications=body.required_qualifications,
        content_category=body.content_category,
    )
    return {"content": row}


@admin_router.get("/v1/admin/tenant-content/review-queue")
async def admin_review_queue(request: Request):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    rows = db.tenant_content_list(tid, status="in_review")
    return {"items": rows}


@admin_router.get("/v1/admin/tenant-content/{content_id}")
async def admin_get_tenant_content(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = db.tenant_content_get(cid, tid)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    return {"content": row}


@admin_router.patch("/v1/admin/tenant-content/{content_id}")
async def admin_patch_tenant_content(
    request: Request,
    content_id: str,
    body: TenantContentPatchBody,
):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.update_content(
        tenant_id=tid,
        content_id=cid,
        user_id=user.id,
        title=body.title,
        body_md=body.body_md,
        slug=body.slug,
        disclaimer_level=body.disclaimer_level,
        vertical_profile=body.vertical_profile,
        target_profession_roles=body.target_profession_roles,
        target_departments=body.target_departments,
        required_qualifications=body.required_qualifications,
        content_category=body.content_category,
    )
    return {"content": row}


@admin_router.post("/v1/admin/tenant-content/{content_id}/publish")
async def admin_publish_tenant_content(
    request: Request,
    content_id: str,
    override: bool = Query(default=False),
):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return _publish_or_http_error(tenant_id=tid, user_id=user.id, content_id=cid, override=override)


@admin_router.post("/v1/admin/tenant-content/{content_id}/submit-for-review")
async def admin_submit_for_review(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return cms.submit_for_review(tenant_id=tid, user_id=user.id, content_id=cid)


@admin_router.post("/v1/admin/tenant-content/{content_id}/approve")
async def admin_approve_content(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.approve_content(tenant_id=tid, user_id=user.id, content_id=cid)
    return {"content": row}


@admin_router.post("/v1/admin/tenant-content/{content_id}/reject")
async def admin_reject_content(request: Request, content_id: str, body: TenantContentRejectBody):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.reject_content(tenant_id=tid, user_id=user.id, content_id=cid, comment=body.comment)
    return {"content": row}


@admin_router.get("/v1/admin/tenant-content/{content_id}/versions")
async def admin_list_versions(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    items = cms.list_versions(tenant_id=tid, content_id=cid, user_id=user.id)
    return {"items": items}


@admin_router.get("/v1/admin/tenant-content/{content_id}/versions/diff")
async def admin_version_diff(
    request: Request,
    content_id: str,
    from_version: int = Query(..., ge=1),
    to_version: int = Query(..., ge=1),
):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    return cms.version_diff(
        tenant_id=tid,
        content_id=cid,
        user_id=user.id,
        from_version=from_version,
        to_version=to_version,
    )


@admin_router.get("/v1/admin/tenant-content/{content_id}/audit")
async def admin_content_audit(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    items = cms.list_audit_events(tenant_id=tid, content_id=cid, user_id=user.id)
    return {"items": items}


@admin_router.post("/v1/admin/tenant-content/{content_id}/archive")
async def admin_archive_tenant_content(request: Request, content_id: str):
    user = await require_site_admin(request)
    tid = _tenant_id_for(user)
    cid = _parse_content_id(content_id)
    row = cms.archive_content(tenant_id=tid, user_id=user.id, content_id=cid)
    return {"content": row}


@router.get("/v1/tenant-content/{slug}")
async def get_published_tenant_content(request: Request, slug: str):
    """Published note for the caller's tenant (search companion / tools)."""
    user = await get_current_user(request)
    tid = _tenant_id_for(user)
    row = db.tenant_content_get_published_by_slug(tid, slug)
    if not row:
        raise HTTPException(status_code=404, detail="content not found")
    policy = effective_policy(user.id, tid)
    if not content_visible_to_policy(row, policy):
        raise HTTPException(status_code=404, detail="content not found")
    return {"content": row}
