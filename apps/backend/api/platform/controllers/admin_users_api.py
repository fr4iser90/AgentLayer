from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from psycopg.types.json import Json
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.platform.use_cases.platform_controller_services import db
from apps.backend.application.tenant_provisioning.use_cases import tenant_provision_controller_services as tenant_prov
from apps.backend.application.identity.use_cases.request_auth import (
    LoginRequest,
    create_access_token,
    create_refresh_token,
    create_user,
    get_current_user,
    get_user_by_email,
    get_user_by_id,
    get_user_for_bearer_token,
    list_all_users,
    require_site_admin,
    require_admin_capability,
    require_admin_scope,
    revoke_refresh_token,
    update_user_tenant,
    validate_refresh_token,
    verify_password,
)
from apps.backend.domain.access.capabilities import AdminScopeError, CAP_USER_MANAGE
from apps.backend.domain.access.tenant_ownership import TenantOwnedEntitiesConflict
from apps.backend.domain.shared.identity import reset_identity, set_identity
from apps.backend.domain.shared.http_identity import resolve_chat_identity
from apps.backend.application.platform.use_cases.platform_controller_services import http_500_detail
from apps.backend.api.platform.controllers.optional_http_access import public_http_auth_policy

router = APIRouter()
logger = logging.getLogger(__name__)

class AdminCreateUserBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=256)
    role: Literal["user", "admin"] = "user"
    tenant_id: int = Field(default=1, ge=1)


class AdminCreateTenantBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    template_id: str | None = Field(default=None, max_length=64)
    seed_demo_content: bool = False


class AdminPatchUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    workspace_quota: int | None = Field(default=None, ge=1, le=1000)
    workspace_self_allowed: bool | None = None
    schedules_allowed: bool | None = None
    dashboards_allowed: bool | None = None
    dashboard_quota: int | None = Field(default=None, ge=1, le=1000)
    media_storage_quota_mb: int | None = Field(default=None, ge=1, le=50_000)
    media_enabled: bool | None = None
    media_upload_enabled: bool | None = None
    media_sharing_enabled: bool | None = None
    llm_queue_priority: int | None = Field(default=None, ge=0, le=1000)
    capabilities: list[str] | None = None


@router.get("/v1/admin/tenant-templates")
async def admin_list_tenant_templates(request: Request):
    """List tenant blueprint templates (Task 07)."""
    await require_site_admin(request)
    return {"items": tenant_prov.list_templates_public()}


@router.get("/v1/admin/tenants")
async def admin_list_tenants(request: Request):
    """List tenants (``tenants.id`` = value for tool allowlists and ``users.tenant_id``)."""
    await require_site_admin(request)
    return {"tenants": db.tenants_list()}


@router.post("/v1/admin/tenants")
async def admin_create_tenant(request: Request, body: AdminCreateTenantBody):
    """Create a tenant; optional ``template_id`` clones org config (Task 07)."""
    await require_site_admin(request)
    if body.seed_demo_content and not body.template_id:
        raise HTTPException(status_code=400, detail="seed_demo_content requires template_id")
    user = await get_current_user(request)
    try:
        out = tenant_prov.provision.provision_tenant(
            name=body.name,
            template_id=body.template_id,
            seed_demo_content=body.seed_demo_content,
            actor_user_id=user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("admin_create_tenant failed")
        raise HTTPException(status_code=500, detail=http_500_detail(e)) from e
    return {"ok": True, **out}


@router.get("/v1/admin/users")
async def admin_list_users(request: Request):
    """List users the caller may administer.

    A delegated ``user.manage`` holder sees only their own tenant; a site admin
    sees all. Before this the endpoint returned every mailbox on the instance to
    any capability holder.
    """
    scope = await require_admin_scope(request, CAP_USER_MANAGE)
    return {"users": list_all_users(tenant_ids=scope.tenant_filter())}


@router.patch("/v1/admin/users/{user_id}")
async def admin_patch_user(request: Request, user_id: uuid.UUID, body: AdminPatchUserBody):
    """Update quotas, media flags, ``capabilities`` and (for site admins) more.

    A delegated ``user.manage`` holder may edit a non-site-admin user inside
    their own tenant only. Moving a user to a different tenant is site-admin
    only; sending the caller's own ``tenant_id`` unchanged is allowed so the
    admin UI can post the row back verbatim.
    """
    # tenant-scope: guarded by require_admin_scope plus the site-admin and
    # target-tenant checks below, not by tenant_id in each UPDATE.
    actor = await require_admin_scope(request, CAP_USER_MANAGE)
    if (
        body.tenant_id is None
        and body.workspace_quota is None
        and body.workspace_self_allowed is None
        and body.schedules_allowed is None
        and body.dashboards_allowed is None
        and body.dashboard_quota is None
        and body.media_storage_quota_mb is None
        and body.media_enabled is None
        and body.media_upload_enabled is None
        and body.media_sharing_enabled is None
        and body.llm_queue_priority is None
        and body.capabilities is None
    ):
        raise HTTPException(status_code=400, detail="no fields to patch")
    u = get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")

    # P6 (Weg B): a delegated ``user.manage`` holder must never touch a site admin.
    if db.user_site_role(u.id) == "site_admin" and not actor.site_wide:
        raise HTTPException(status_code=403, detail="only a site admin can modify a site admin")

    # The target must live inside the caller's tenant scope.
    target_tenant = int(db.user_tenant_id(u.id) or 1)
    if not actor.allows_tenant(target_tenant):
        raise HTTPException(status_code=403, detail="user is outside your admin scope")

    try:
        if body.tenant_id is not None and int(body.tenant_id) != target_tenant:
            # Moving a person between companies is never a delegated action.
            actor.require_site_wide("moving a user between tenants")
            if not db.tenant_exists(body.tenant_id):
                raise HTTPException(status_code=400, detail="unknown tenant_id")
            if not update_user_tenant(user_id, body.tenant_id):
                raise HTTPException(status_code=404, detail="user not found")
    except TenantOwnedEntitiesConflict as exc:
        # Not a permission failure — the actor may be entitled to move this
        # person and still be blocked until the company's entities are handed
        # over. 404 would be a lie here, so the counts go out verbatim.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AdminScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if body.workspace_quota is not None:
        db.query(
            "UPDATE users SET workspace_quota = %s WHERE id = %s",
            (body.workspace_quota, user_id),
        )

    if body.workspace_self_allowed is not None:
        db.query(
            "UPDATE users SET workspace_self_allowed = %s WHERE id = %s",
            (body.workspace_self_allowed, user_id),
        )

    if body.schedules_allowed is not None:
        db.query(
            "UPDATE users SET schedules_allowed = %s WHERE id = %s",
            (body.schedules_allowed, user_id),
        )

    if body.dashboards_allowed is not None:
        db.query(
            "UPDATE users SET dashboards_allowed = %s WHERE id = %s",
            (body.dashboards_allowed, user_id),
        )
        if body.dashboards_allowed is False:
            # P4: revoke dashboard access — remove the user's dashboards so none are retained.
            try:
                from apps.backend.application.dashboards.use_cases.dashboard_controller_services import (
                    delete_user_dashboards,
                )

                delete_user_dashboards(user_id)
            except Exception:
                logger.warning(
                    "dashboards revoke: delete failed for user %s", user_id, exc_info=True
                )

    if body.dashboard_quota is not None:
        db.query(
            "UPDATE users SET dashboard_quota = %s WHERE id = %s",
            (body.dashboard_quota, user_id),
        )

    if body.media_storage_quota_mb is not None:
        db.query(
            "UPDATE users SET media_storage_quota_mb = %s WHERE id = %s",
            (body.media_storage_quota_mb, user_id),
        )

    if body.media_enabled is not None:
        db.query(
            "UPDATE users SET media_enabled = %s WHERE id = %s",
            (body.media_enabled, user_id),
        )

    if body.media_upload_enabled is not None:
        db.query(
            "UPDATE users SET media_upload_enabled = %s WHERE id = %s",
            (body.media_upload_enabled, user_id),
        )

    if body.media_sharing_enabled is not None:
        db.query(
            "UPDATE users SET media_sharing_enabled = %s WHERE id = %s",
            (body.media_sharing_enabled, user_id),
        )

    if "llm_queue_priority" in body.model_fields_set:
        db.query(
            "UPDATE users SET llm_queue_priority = %s WHERE id = %s",
            (body.llm_queue_priority, user_id),
        )
        try:
            from apps.backend.application.platform.use_cases.platform_controller_services import invalidate_user_priority_cache

            invalidate_user_priority_cache(user_id)
        except Exception:
            pass

    if body.capabilities is not None:
        from apps.backend.domain.access.capabilities import ALL_ADMIN_CAPABILITIES

        norm = sorted({str(c).strip().lower() for c in body.capabilities if str(c).strip()})
        unknown = [c for c in norm if c not in ALL_ADMIN_CAPABILITIES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown capabilities: {unknown}")
        db.query(
            "UPDATE users SET capabilities = %s WHERE id = %s",
            (Json(norm), user_id),
        )

    return {
        "ok": True,
        "id": str(user_id),
        "tenant_id": db.user_tenant_id(user_id),
    }


@router.post("/v1/admin/users")
async def admin_create_user(request: Request, body: AdminCreateUserBody):
    """Create a password user (e.g. role ``user``).

    A delegated ``user.manage`` holder may create regular users only inside their
    own tenant, and never a site admin (``role=admin`` maps to
    ``site_role=site_admin``).
    """
    actor = await require_admin_scope(request, CAP_USER_MANAGE)
    if body.role == "admin" and not actor.site_wide:
        raise HTTPException(status_code=403, detail="only a site admin can create a site admin")
    try:
        tenant_id = actor.require_tenant(body.tenant_id, what="target tenant")
    except AdminScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not db.tenant_exists(tenant_id):
        raise HTTPException(status_code=400, detail="unknown tenant_id")
    if get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="email already registered")
    u = create_user(body.email, body.password, body.role, tenant_id=tenant_id)
    return {"ok": True, "id": str(u.id), "email": u.email, "role": u.role, "tenant_id": tenant_id}


@router.get("/auth/policy")
def http_auth_policy():
    """Public JSON: path classes, middleware auth behavior, admin routes, client surfaces."""
    out = public_http_auth_policy()
    try:
        from apps.backend.application.platform.use_cases.client_surface_policy import public_policy

        out["client_surface"] = public_policy()
    except Exception:
        pass
    return out
