"""Dashboard membership, block share, and public share endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from apps.backend.api.dashboards.controllers.dashboard_common import (
    DashboardBlockShareBody,
    DashboardMemberAddBody,
    DashboardPublicShareCreateBody,
    require_dashboard_schema,
)
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_db
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import public_share
from apps.backend.application.identity.use_cases.request_auth import get_current_user, get_user_by_email

router = APIRouter()

@router.get("/{dashboard_id}/members")
async def list_dashboard_members(request: Request, dashboard_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    acc = dashboard_db.dashboard_access(user.id, tid, dashboard_id)
    if acc is None:
        raise HTTPException(status_code=404, detail="dashboard not found")
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list members")
    items = dashboard_db.members_list(user.id, tid, dashboard_id)
    return {"ok": True, "members": items}


@router.post("/{dashboard_id}/members")
async def add_dashboard_member(
    request: Request, dashboard_id: uuid.UUID, body: DashboardMemberAddBody
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can add members")
    target = get_user_by_email(body.email.strip().lower())
    if target is None:
        raise HTTPException(status_code=404, detail="user not found for this email")
    if db.user_tenant_id(target.id) != tid:
        raise HTTPException(status_code=400, detail="user must be in the same tenant")
    role = (body.role or "viewer").strip().lower()
    if role not in ("viewer", "editor", "co_owner"):
        raise HTTPException(status_code=400, detail="role must be viewer, editor, or co_owner")
    ok = dashboard_db.member_add(user.id, tid, dashboard_id, target.id, role)
    if not ok:
        raise HTTPException(status_code=400, detail="could not add member")
    return {"ok": True, "members": dashboard_db.members_list(user.id, tid, dashboard_id)}


@router.delete("/{dashboard_id}/members/{member_user_id}")
async def remove_dashboard_member(
    request: Request, dashboard_id: uuid.UUID, member_user_id: uuid.UUID
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can remove members")
    if not dashboard_db.member_remove(user.id, tid, dashboard_id, member_user_id):
        raise HTTPException(status_code=404, detail="member not found")
    return {"ok": True, "removed": True}


@router.get("/{dashboard_id}/block-shares")
async def list_dashboard_block_shares(request: Request, dashboard_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list block shares")
    items = dashboard_db.block_share_grants_list(user.id, tid, dashboard_id)
    return {"ok": True, "grants": items}


@router.post("/{dashboard_id}/block-shares")
async def upsert_dashboard_block_share(
    request: Request, dashboard_id: uuid.UUID, body: DashboardBlockShareBody
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    target = get_user_by_email(body.email.strip().lower())
    if target is None:
        raise HTTPException(status_code=404, detail="user not found for this email")
    perm = (body.permission or "view").strip().lower()
    if perm not in ("view", "edit"):
        raise HTTPException(status_code=400, detail="permission must be view or edit")
    ok = dashboard_db.block_share_grant_upsert(
        user.id,
        tid,
        dashboard_id,
        viewer_user_id=target.id,
        block_ids=body.block_ids,
        permission=perm,
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="could not save (check block ids exist in layout, not owner email, same tenant)",
        )
    items = dashboard_db.block_share_grants_list(user.id, tid, dashboard_id)
    return {"ok": True, "grants": items}


@router.delete("/{dashboard_id}/block-shares/{viewer_user_id}")
async def delete_dashboard_block_share(
    request: Request, dashboard_id: uuid.UUID, viewer_user_id: uuid.UUID
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can remove block shares")
    if not dashboard_db.block_share_grant_delete(user.id, tid, dashboard_id, viewer_user_id):
        raise HTTPException(status_code=404, detail="grant not found")
    return {"ok": True, "removed": True}


@router.get("/{dashboard_id}/public-shares")
async def list_dashboard_public_shares(request: Request, dashboard_id: uuid.UUID):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can list public shares")
    items = public_share.public_share_list(user.id, tid, dashboard_id)
    return {"ok": True, "shares": items}


@router.post("/{dashboard_id}/public-shares")
async def create_dashboard_public_share(
    request: Request, dashboard_id: uuid.UUID, body: DashboardPublicShareCreateBody
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    expires_at = None
    if body.expires_at:
        raw_exp = body.expires_at.strip()
        if raw_exp:
            try:
                expires_at = datetime.fromisoformat(raw_exp.replace("Z", "+00:00"))
            except ValueError as e:
                raise HTTPException(status_code=400, detail="expires_at must be ISO-8601") from e
    if body.password is not None and body.password.strip() and len(body.password.strip()) < 4:
        raise HTTPException(status_code=400, detail="password must be at least 4 characters")
    created = public_share.public_share_create(
        user.id,
        tid,
        dashboard_id,
        block_ids=body.block_ids,
        label=body.label,
        expires_at=expires_at,
        password=body.password,
    )
    if created is None:
        raise HTTPException(
            status_code=400,
            detail="could not create share (check block ids or permissions)",
        )
    raw_token, meta = created
    share_url = f"/app/dashboard/shared?t={raw_token}"
    return {
        "ok": True,
        "share": {**meta, "url_path": share_url},
        "token": raw_token,
    }


@router.delete("/{dashboard_id}/public-shares/{share_id}")
async def revoke_dashboard_public_share(
    request: Request, dashboard_id: uuid.UUID, share_id: uuid.UUID
):
    require_dashboard_schema()
    user = await get_current_user(request)
    tid = db.user_tenant_id(user.id)
    if not dashboard_db.dashboard_can_manage_members(user.id, tid, dashboard_id):
        raise HTTPException(status_code=403, detail="only owner or co-owner can revoke public shares")
    if not public_share.public_share_revoke(user.id, tid, dashboard_id, share_id):
        raise HTTPException(status_code=404, detail="share not found")
    return {"ok": True, "revoked": True}
