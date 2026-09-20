"""
Share Permissions API

Granular permission system for managing who can access what from whom.
Completely generic for all resource types - calendar, github, notes, agents etc.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.domain.shares.catalog import catalog_for_api, canonical_resource_type
from apps.backend.domain.shares.policy import normalize_policy
from apps.backend.domain.shares.projections import (
    default_projection_kind,
    projection_backed,
    projection_kinds_for,
    projection_store,
)
from apps.backend.domain.shares.registry import (
    canonical_type_for,
    get_share_adapter,
    publish_projection,
    resolve_projection,
)
from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.sharing.use_cases.sharing_controller_services import friend_get
from apps.backend.application.sharing.use_cases.sharing_controller_services import (
    list_shares_between,
    list_shares_by_grantee,
    list_shares_by_owner,
    require_friend_system,
    share_permission_check,
    share_permission_set,
)

router = APIRouter(
    prefix="/v1/shares",
    tags=["shares"],
    dependencies=[Depends(require_friend_system)],
)


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


class ProjectionPublishBody(BaseModel):
    resource_type: str = Field(..., min_length=2, max_length=50)
    resource_identifier: str = Field(default="primary", min_length=1, max_length=100)
    projection_kind: str | None = Field(default=None, min_length=1, max_length=50)


@router.post("/projection")
async def publish_share_projection(request: Request, body: ProjectionPublishBody):
    """Publish the caller's own narrowed view of a resource (ADR 0014 step 6).

    Owner-side and deliberately separate from ``/set``: this chooses *what
    shape exists*, not *who may read it*. Publishing grants nothing, and a
    projection nobody has been granted is still unreadable.
    """
    user = await get_current_user(request)

    canonical = canonical_resource_type(body.resource_type)
    if not canonical:
        raise HTTPException(status_code=400, detail="invalid resource_type")

    adapter = get_share_adapter(canonical)
    if adapter is None:
        raise HTTPException(
            status_code=404, detail="no adapter registered for this resource_type"
        )

    kinds = projection_kinds_for(adapter)
    if not kinds:
        raise HTTPException(
            status_code=400,
            detail="this resource is read live and publishes no projections",
        )

    kind = (body.projection_kind or default_projection_kind(adapter) or "").strip().lower()
    if kind not in kinds:
        raise HTTPException(
            status_code=400,
            detail=f"unknown projection_kind '{kind}'; available: {', '.join(kinds)}",
        )

    outcome = publish_projection(
        resource_type=canonical,
        owner_user_id=user.id,
        identifier=body.resource_identifier,
        kind=kind,
    )
    if not outcome.served:
        raise HTTPException(status_code=422, detail=outcome.refusal or "publish_failed")

    stored = outcome.projection
    return {
        "ok": True,
        "resource_type": canonical,
        "resource_identifier": body.resource_identifier,
        "projection_kind": stored.kind,
        "expires_at": stored.expires_at.isoformat() if stored.expires_at else None,
        "available_kinds": list(kinds),
    }


@router.get("/projections")
async def list_my_share_projections(request: Request):
    """What the caller has published about their own resources.

    Owner-scoped, and deliberately not part of the per-friend grant list.
    The projection shape is a property of the resource, not of the share:
    one row per (owner, type, identifier), and every grantee of that
    resource sees the same shape. Putting the picker next to a particular
    friend would imply Lena can give Bob the narrow view and Alice the
    wide one, which is neither what the model does nor what she would
    have agreed to.
    """
    user = await get_current_user(request)
    store = projection_store()
    if store is None:
        return {"ok": True, "projections": []}

    now = datetime.now(timezone.utc)
    items: list[dict[str, Any]] = []
    for row in store.projection_list_for_owner(owner_user_id=user.id):
        adapter = get_share_adapter(str(row.get("resource_type") or ""))
        expires = row.get("expires_at")
        generated = row.get("generated_at")
        items.append(
            {
                "resource_type": row.get("resource_type"),
                "resource_identifier": row.get("resource_identifier"),
                "projection_kind": row.get("projection_kind"),
                # Sent with each row rather than only in the catalog, so the
                # picker can offer a change without a second round-trip and
                # cannot offer a kind this adapter never publishes.
                "available_kinds": list(projection_kinds_for(adapter)) if adapter else [],
                "default_kind": default_projection_kind(adapter) if adapter else None,
                "generated_at": generated.isoformat() if generated else None,
                "expires_at": expires.isoformat() if expires else None,
                "fresh": bool(expires) and expires > now,
            }
        )
    return {"ok": True, "projections": items}


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


# A registry refusal is a fact about why nothing was served, and the three
# a grantee can act on are different: ask for the grant, fix the
# identifier, or stop — so they cannot share one status code.
_PREVIEW_REFUSAL_STATUS = {
    "no_adapter_registered": 404,
    "malformed_identifier": 400,
    "not_granted": 403,
}


@router.get("/preview/{resource_type}")
async def preview_shared_resource(
    request: Request,
    resource_type: str,
    owner_user_id: str,
    identifier: str = "",
    days: int | None = None,
):
    """Generic preview of a friend's shared resource, for dashboard widgets.

    Resolved through the registry rather than reimplemented here. That is
    the whole point of this endpoint: the grant is enforced by the adapter
    that owns the type, and what comes back is the projection the owner
    published.

    The calendar-only preview this replaces checked the grant again in the
    controller and then fetched the live feed. Two consequences, both
    wrong: the owner's chosen shape was ignored, so a friend who had been
    given ``availability`` — busy windows, no titles — still had event
    titles rendered from a live ICS read; and every widget load was a
    round-trip to the owner's source, leaving the projection machinery
    doing nothing for the one surface that reads most often.

    Previewable means projection-backed. A type with an adapter but no
    projection reads live and returns a permission decision rather than
    content, so there is nothing for a widget to draw.
    """
    user = await get_current_user(request)
    try:
        owner_uuid = uuid.UUID(owner_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid owner_user_id")

    adapter = get_share_adapter(resource_type)
    if adapter is None:
        raise HTTPException(status_code=404, detail="unknown resource type")
    if not projection_backed(adapter):
        raise HTTPException(status_code=404, detail="resource type is not previewable")

    resolved_identifier = identifier or (adapter.normalize_identifier("") or "")
    if not resolved_identifier:
        raise HTTPException(status_code=400, detail="identifier required")

    outcome = resolve_projection(
        resource_type=resource_type,
        owner_user_id=owner_uuid,
        grantee_user_id=user.id,
        identifier=resolved_identifier,
        request={} if days is None else {"days": days},
    )
    if not outcome.served:
        raise HTTPException(
            status_code=_PREVIEW_REFUSAL_STATUS.get(outcome.refusal or "", 400),
            detail=outcome.refusal,
        )

    return {
        "ok": True,
        # The adapter's canonical id, not the string that arrived: a
        # request made under the legacy ``calendar`` alias should not come
        # back looking like a second, different resource type.
        "resource_type": canonical_type_for(adapter, resource_type),
        "owner_user_id": owner_user_id,
        "preview": outcome.projection,
    }
