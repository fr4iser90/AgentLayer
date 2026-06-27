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
from pydantic import BaseModel, ConfigDict, Field

from apps.backend.application.platform.use_cases.platform_controller_services import db
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
    require_admin,
    revoke_refresh_token,
    update_user_tenant,
    validate_refresh_token,
    verify_password,
)
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


class AdminPatchUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: int | None = Field(default=None, ge=1)
    workspace_quota: int | None = Field(default=None, ge=1, le=1000)
    workspace_self_allowed: bool | None = None
    media_storage_quota_mb: int | None = Field(default=None, ge=1, le=50_000)
    media_enabled: bool | None = None
    media_upload_enabled: bool | None = None
    media_sharing_enabled: bool | None = None
    llm_queue_priority: int | None = Field(default=None, ge=0, le=1000)


@router.get("/v1/admin/tenants")
async def admin_list_tenants(request: Request):
    """List tenants (``tenants.id`` = value for tool allowlists and ``users.tenant_id``)."""
    await require_admin(request)
    return {"tenants": db.tenants_list()}


@router.post("/v1/admin/tenants")
async def admin_create_tenant(request: Request, body: AdminCreateTenantBody):
    """Create a tenant (e.g. work / friends). Admin only."""
    await require_admin(request)
    row = db.tenant_insert(body.name)
    return {"ok": True, "tenant": row}


@router.get("/v1/admin/users")
async def admin_list_users(request: Request):
    """List all users (admin UI); ``email`` may be empty when the row has no mailbox."""
    await require_admin(request)
    return {"users": list_all_users()}


@router.patch("/v1/admin/users/{user_id}")
async def admin_patch_user(request: Request, user_id: uuid.UUID, body: AdminPatchUserBody):
    """Update ``tenant_id``, ``workspace_quota``, ``workspace_self_allowed``. Admin only."""
    await require_admin(request)
    if body.tenant_id is None and body.workspace_quota is None and body.workspace_self_allowed is None and body.media_storage_quota_mb is None and body.media_enabled is None and body.media_upload_enabled is None and body.media_sharing_enabled is None and body.llm_queue_priority is None:
        raise HTTPException(status_code=400, detail="no fields to patch")
    u = get_user_by_id(user_id)
    if not u:
        raise HTTPException(status_code=404, detail="user not found")

    if body.tenant_id is not None:
        if not db.tenant_exists(body.tenant_id):
            raise HTTPException(status_code=400, detail="unknown tenant_id")
        if not update_user_tenant(user_id, body.tenant_id):
            raise HTTPException(status_code=404, detail="user not found")

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

    return {
        "ok": True,
        "id": str(user_id),
        "tenant_id": db.user_tenant_id(user_id),
    }


@router.post("/v1/admin/users")
async def admin_create_user(request: Request, body: AdminCreateUserBody):
    """Create a password user (e.g. role ``user``). Admin only."""
    await require_admin(request)
    if not db.tenant_exists(body.tenant_id):
        raise HTTPException(status_code=400, detail="unknown tenant_id")
    if get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="email already registered")
    u = create_user(body.email, body.password, body.role, tenant_id=body.tenant_id)
    return {"ok": True, "id": str(u.id), "email": u.email, "role": u.role, "tenant_id": body.tenant_id}


@router.get("/auth/policy")
def http_auth_policy():
    """Public JSON: path classes, middleware auth behavior, admin routes."""
    return public_http_auth_policy()
