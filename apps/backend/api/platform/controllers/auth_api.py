from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Literal

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
from apps.backend.application.platform.use_cases.platform_controller_services import (
    apply_setup_deployment_mode,
    apply_setup_llm_endpoint,
    build_setup_status,
    create_first_admin,
    enforce_setup_rate_limit,
    operator_settings,
    probe_llm_endpoint,
    validate_setup_email,
    validate_setup_password,
    validate_setup_token,
)
from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
    effective_policy,
    ensure_tenant_profession_defaults,
)
from apps.backend.application.platform.use_cases.platform_controller_services import (
    SetupPreferencesBody,
    apply_enable_chat_provider_embedding,
    apply_setup_preferences,
    apply_setup_skip_suggestions,
    build_setup_catalog,
    test_embedding_model,
)

router = APIRouter()
logger = logging.getLogger(__name__)
REFRESH_COOKIE_NAME = "agent_refresh"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600


def _cookie_secure(request: Request) -> bool:
    raw = (os.environ.get("AGENT_COOKIE_SECURE") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    if (request.url.scheme or "").lower() == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return proto == "https"

def _auth_session_response(request: Request, user: Any) -> JSONResponse:
    access_token = create_access_token(user.id, user.role)
    refresh_token, refresh_token_hash = create_refresh_token(user.id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
                VALUES (%s, %s, NOW() + INTERVAL '7 days')
                """,
                (user.id, refresh_token_hash),
            )
            conn.commit()
    payload = {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
        },
    }
    response = JSONResponse(content=payload)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE,
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
    )
    return response


@router.post("/auth/login")
async def login(request: Request, login_data: LoginRequest):
    user = get_user_by_email(login_data.email)
    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_session_response(request, user)


@router.post("/auth/refresh")
async def auth_refresh(request: Request):
    raw_refresh = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh:
        try:
            body = await request.json()
            if isinstance(body, dict):
                raw_refresh = body.get("refresh_token")
        except Exception:
            pass
    if not raw_refresh:
        raise HTTPException(status_code=400, detail="refresh_token required")

    user = validate_refresh_token(raw_refresh)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = create_access_token(user.id, user.role)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/auth/logout")
async def auth_logout(request: Request):
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
        revoke_refresh_token(raw)
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/")
    return response


class AuthSetupDeploymentModeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deployment_mode: Literal["agent_system", "multi_tenant"]
    setup_token: str


class AuthSetupBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    password: str
    password_confirm: str
    setup_token: str


class AuthSetupLlmBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    api_key: str | None = None
    model_default: str | None = None
    label: str | None = None
    test_only: bool = False


@router.get("/auth/setup-status")
async def auth_setup_status():
    """Initial instance configuration state (admin account, LLM catalog)."""
    return build_setup_status()


@router.post("/auth/setup/deployment-mode")
async def auth_setup_deployment_mode(request: Request, body: AuthSetupDeploymentModeBody):
    """Choose agent_system vs multi_tenant before first admin is created."""
    enforce_setup_rate_limit(request)
    validate_setup_token(body.setup_token)
    return apply_setup_deployment_mode(deployment_mode=body.deployment_mode)


@router.post("/auth/setup")
async def auth_setup(request: Request, body: AuthSetupBody):
    """Create the first administrator (only while no admin exists)."""
    enforce_setup_rate_limit(request)
    validate_setup_token(body.setup_token)
    validate_setup_email(body.email)
    validate_setup_password(body.password, body.password_confirm)
    user = create_first_admin(email=body.email, password=body.password)
    return _auth_session_response(request, user)


@router.post("/auth/setup/llm")
async def auth_setup_llm(request: Request, body: AuthSetupLlmBody):
    """Configure or test the OpenAI-compatible LLM endpoint (admin session required)."""
    await require_admin(request)
    if body.test_only:
        return await probe_llm_endpoint(base_url=body.base_url, api_key=body.api_key)
    probe = await probe_llm_endpoint(base_url=body.base_url, api_key=body.api_key)
    apply_setup_llm_endpoint(
        base_url=body.base_url,
        api_key=body.api_key,
        model_default=body.model_default,
        label=body.label,
    )
    return {
        "ok": True,
        "model_count": probe.get("model_count", 0),
        "models": probe.get("models", []),
    }


@router.get("/auth/setup/catalog")
async def auth_setup_catalog(request: Request):
    """Provider reachability and chat/embedding model lists for setup step 2."""
    await require_admin(request)
    return build_setup_catalog()


class AuthSetupPreferencesBody(SetupPreferencesBody):
    """Alias for OpenAPI; fields defined on SetupPreferencesBody."""


@router.post("/auth/setup/preferences")
async def auth_setup_preferences(request: Request, body: AuthSetupPreferencesBody):
    """Persist preferred provider and profile models (general, coding, embedding)."""
    await require_admin(request)
    return apply_setup_preferences(body)


class AuthSetupTestEmbeddingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., min_length=1, max_length=256)


@router.post("/auth/setup/test-embedding")
async def auth_setup_test_embedding(request: Request, body: AuthSetupTestEmbeddingBody):
    """Probe embedding dimension for a model id on the configured embedding API."""
    await require_admin(request)
    return await test_embedding_model(body.model)


@router.post("/auth/setup/skip-profiles")
async def auth_setup_skip_profiles(request: Request):
    """Skip provider wizard step; persist catalog suggestions when a chat provider is reachable."""
    await require_admin(request)
    return apply_setup_skip_suggestions()


@router.post("/auth/setup/enable-chat-provider-embedding")
async def auth_setup_enable_chat_provider_embedding(request: Request):
    """Opt-in: use chat provider host for embeddings (operator_settings)."""
    await require_admin(request)
    return apply_enable_chat_provider_embedding()


@router.get("/auth/me")
async def get_current_user_info(request: Request):
    """
    Current session user. Implemented without ``require_permission`` so FastAPI does not treat a
    bare ``user`` parameter as request-body injection (that caused 422).
    """
    user = await get_current_user(request)
    discord_uid = db.user_discord_user_id_get(user.id)
    telegram_uid = db.user_telegram_user_id_get(user.id)
    tid = db.user_tenant_id(user.id)
    tenant_row = db.tenant_get(tid)
    deployment = operator_settings.deployment_mode()
    site_role = db.user_site_role(user.id)
    membership = db.user_membership_role(user.id, tid)
    setup_required = (
        deployment == "multi_tenant"
        and membership in ("tenant_owner", "tenant_admin")
        and tenant_row is not None
        and tenant_row.get("setup_completed_at") is None
    )
    base = {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "site_role": site_role,
        "tenant_id": tid,
        "membership_role": membership,
        "deployment_mode": deployment,
        "org_setup_required": setup_required,
        "vertical_profile": (tenant_row or {}).get("vertical_profile"),
        "created_at": user.created_at.isoformat(),
        "discord_user_id": discord_uid,
        "telegram_user_id": telegram_uid,
    }
    if deployment == "multi_tenant" and membership:
        ensure_tenant_profession_defaults(tid)
        base["profession_policy"] = effective_policy(user.id, tid).to_public_dict()
    if site_role != "site_admin":
        id_token = set_identity(1, user.id)
        try:
            return _enrich_capability_fields(base, tid)
        finally:
            reset_identity(id_token)
    return _enrich_capability_fields(base, tid)


def _enrich_capability_fields(base: dict, tid: int) -> dict:
    from apps.backend.domain.tenant_capability.policy import (
        tenant_allowed_nav_items,
        tenant_can_structure_edit_dashboards,
    )

    nav = tenant_allowed_nav_items(tid)
    if nav is not None:
        base["allowed_nav"] = sorted(nav)
    membership = base.get("membership_role")
    base["dashboard_structure_edit"] = tenant_can_structure_edit_dashboards(
        tid, str(membership) if membership else None
    )
    return base
