"""
Share Permissions API

Granular permission system for managing who can access what from whom.
Completely generic for all resource types - calendar, github, notes, agents etc.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.shares.catalog import catalog_for_api, canonical_resource_type
from apps.backend.domain.shares.policy import normalize_policy
from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.db.friends_db import friend_get
from apps.backend.infrastructure.db.share_permissions_db import (
    SHARE_RESOURCE_GOOGLE_CALENDAR,
    list_shares_between,
    list_shares_by_grantee,
    list_shares_by_owner,
    share_permission_check,
    share_permission_get,
    share_permission_set,
)

router = APIRouter(prefix="/v1/shares", tags=["shares"])


class ShareSetBody(BaseModel):
    grantee_user_id: str = Field(..., min_length=36, max_length=36)
    resource_type: str = Field(..., min_length=2, max_length=50)
    resource_identifier: str = Field(default="primary", min_length=1, max_length=100)
    is_allowed: bool = Field(...)
    policy: dict[str, Any] | None = Field(default=None)


@router.get("/catalog")
async def get_share_catalog(request: Request, lang: str = "en"):
    """No fixed resource list — share any resource_type string; policy keys are generic."""
    await get_current_user(request)
    _ = lang
    return {"ok": True, "resources": catalog_for_api()}


@router.post("/set")
async def set_share_permission(request: Request, body: ShareSetBody):
    """Set or revoke a specific share permission."""
    user = await get_current_user(request)

    try:
        grantee_uuid = uuid.UUID(body.grantee_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid grantee_user_id")

    if grantee_uuid == user.id:
        raise HTTPException(status_code=400, detail="cannot share with yourself")

    if not friend_get(user.id, grantee_uuid):
        raise HTTPException(status_code=400, detail="grantee is not a confirmed friend")

    canonical = canonical_resource_type(body.resource_type)
    if not canonical:
        raise HTTPException(status_code=400, detail="invalid resource_type")

    clean_policy, policy_err = normalize_policy(canonical, body.policy)
    if policy_err:
        raise HTTPException(status_code=400, detail=policy_err)

    if body.is_allowed and body.policy is None:
        clean_policy = {}

    ok = share_permission_set(
        owner_user_id=user.id,
        grantee_user_id=grantee_uuid,
        resource_type=canonical,
        resource_identifier=body.resource_identifier,
        allowed=body.is_allowed,
        policy=clean_policy if body.is_allowed else None,
    )

    if not ok:
        raise HTTPException(status_code=500, detail="could not update share permission")

    return {"ok": True, "policy": clean_policy if body.is_allowed else {}}


@router.get("/check")
async def check_share_permission(
    request: Request,
    owner_user_id: str,
    grantee_user_id: str,
    resource_type: str,
    resource_identifier: str,
):
    """Check if a specific share permission is active."""
    user = await get_current_user(request)

    try:
        owner_uuid = uuid.UUID(owner_user_id)
        grantee_uuid = uuid.UUID(grantee_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id format")

    if user.id != owner_uuid and user.id != grantee_uuid:
        raise HTTPException(status_code=403, detail="not allowed to check this permission")

    allowed = share_permission_check(
        owner_user_id=owner_uuid,
        grantee_user_id=grantee_uuid,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    )

    return {"ok": True, "allowed": allowed}


@router.get("/outgoing")
async def get_outgoing_shares(request: Request):
    """List all permissions that the current user has granted to others."""
    user = await get_current_user(request)
    shares = list_shares_by_owner(user.id)
    return {"ok": True, "shares": shares}


@router.get("/incoming")
async def get_incoming_shares(request: Request):
    """List all permissions that others have granted to the current user."""
    user = await get_current_user(request)
    shares = list_shares_by_grantee(user.id)
    return {"ok": True, "shares": shares}


@router.get("/friend/{friend_user_id}")
async def get_shares_between_friends(request: Request, friend_user_id: str):
    """Get bidirectional share status between current user and another user."""
    user = await get_current_user(request)

    try:
        friend_uuid = uuid.UUID(friend_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid friend user id")

    if not friend_get(user.id, friend_uuid):
        raise HTTPException(status_code=404, detail="not a confirmed friend")

    shares = list_shares_between(user.id, friend_uuid)
    return {"ok": True, **shares}


@router.get("/preview/calendar")
async def preview_friend_calendar(
    request: Request,
    owner_user_id: str,
    days: int = 7,
):
    """Compact calendar preview for share_widget blocks (requires active grant)."""
    user = await get_current_user(request)
    try:
        owner_uuid = uuid.UUID(owner_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid owner_user_id")

    if not share_permission_check(
        owner_user_id=owner_uuid,
        grantee_user_id=user.id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    ):
        raise HTTPException(status_code=403, detail="calendar not shared with you")

    grant = share_permission_get(
        owner_user_id=owner_uuid,
        grantee_user_id=user.id,
        resource_type=SHARE_RESOURCE_GOOGLE_CALENDAR,
    )
    from apps.backend.domain.shares.policy import effective_days_ahead
    from plugins.tools.integrations.friends.lib.common import friend_calendar_ics_url

    effective = effective_days_ahead(
        grant.get("policy") if grant else None,
        days,
    )

    ics_url = friend_calendar_ics_url(owner_uuid)
    if not ics_url:
        return {"ok": True, "events": [], "hint": "friend has no calendar configured"}

    try:
        from plugins.tools.personal.calendar.ics import calendar_ics

        raw = calendar_ics({"ics_url": ics_url, "days": effective})
        if isinstance(raw, str):
            import json as _json

            parsed = _json.loads(raw)
        else:
            parsed = raw
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "days_effective": effective,
        "calendar": parsed,
    }
