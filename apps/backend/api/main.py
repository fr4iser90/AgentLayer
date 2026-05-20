"""OpenAI-compatible HTTP API: proxies to Ollama and executes local tools."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from apps.backend.core.config import config
from apps.backend.infrastructure.openai_compat_http import http_get_json
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.auth import (
    get_current_user,
    get_user_for_bearer_token,
    list_all_users,
    require_admin,
    LoginRequest,
    create_access_token,
    create_refresh_token,
    verify_password,
    get_user_by_email,
    get_user_by_id,
    create_user,
    update_user_tenant,
    validate_refresh_token,
    revoke_refresh_token,
)
from apps.backend.infrastructure.operator_settings import (
    InterfaceHintsPayload,
    OperatorSettingsPatch,
    OperatorSettingsPayload,
    apply_interface_hints,
    apply_operator_settings_patch,
    apply_update as operator_settings_apply,
    interface_hints_public,
    invalidate_operator_settings_cache,
    public_dict as operator_settings_public,
    resolve_external_llm_credentials_for_catalog,
    external_api_headers,
    external_models_list_url,
)
from apps.backend.api.optional_http_access import (
    is_identity_deferred_route,
    middleware_path_is_public,
    public_http_auth_policy,
)
from apps.backend.domain.admin_setup import is_first_start
from apps.backend.domain.instance_setup import (
    apply_setup_llm_endpoint,
    build_setup_status,
    create_first_admin,
    emit_initial_setup_notice_at_end,
    enforce_setup_rate_limit,
    probe_llm_endpoint,
    setup_admin_claim_if_needed,
    validate_setup_email,
    validate_setup_password,
    validate_setup_token,
)
from apps.backend.domain.setup_catalog import (
    SetupPreferencesBody,
    apply_setup_preferences,
    apply_setup_skip_suggestions,
    build_setup_catalog,
    test_embedding_model,
)
from apps.backend.domain.rag_docs_file_ingest import run_startup_rag_docs_ingest
from apps.backend.domain.agent import WorkspaceAccessDenied, chat_completion
from apps.backend.infrastructure.llm_user_errors import user_visible_llm_transport_error
from apps.backend.domain.http_identity import resolve_chat_identity
from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.tool_invocation_context import bind_capability_confirmed, reset_capability_confirmed
from apps.backend.domain.plugin_system.tools_api import router as tools_router
from apps.backend.api.chat_websocket import router as chat_ws_router
from apps.backend.api.studio_api import router as studio_router
from apps.backend.api.rag_api import router as rag_router
from apps.backend.api.codebase_api import router as codebase_router
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.infrastructure.user_data_api import router as user_data_router
from apps.backend.infrastructure.memory_api import router as memory_router
from apps.backend.infrastructure.user_secrets_api import router as user_secrets_router
from apps.backend.api.conversations_api import router as conversations_router
from apps.backend.dashboard.router import router as dashboard_router
from apps.backend.infrastructure.log_redaction import (
    apply_http_client_log_levels,
    install_log_redaction_filters,
)
from apps.backend.infrastructure.public_error import http_500_detail
# from apps.backend.integrations.pidea.api_router import router as pidea_router
from apps.backend.api.scheduler_jobs_admin_api import router as scheduler_jobs_admin_router
from apps.backend.api.scheduler_job_presets_api import router as scheduler_job_presets_router
from apps.backend.api.scheduler_job_runs_api import admin_router as scheduler_job_runs_admin_router
from apps.backend.api.scheduler_job_runs_api import user_router as scheduler_job_runs_user_router
from apps.backend.api.scheduler_jobs_user_api import router as scheduler_jobs_user_router
from apps.backend.api.scheduler_job_presets_user_api import router as scheduler_job_presets_user_router
from apps.backend.api.project_runs_api import router as project_runs_router
from apps.backend.api.friends_api import router as friends_router
from apps.backend.api.shares_api import router as shares_router
from apps.backend.api.workspaces_api import router as workspaces_router
from apps.backend.api.agents_api import router as agents_router
from apps.backend.api.session_runtime_api import router as session_runtime_router

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
install_log_redaction_filters()
logger = logging.getLogger(__name__)

REFRESH_COOKIE_NAME = "agent_refresh"
REFRESH_COOKIE_MAX_AGE = 7 * 24 * 3600


def _cookie_secure(request: Request) -> bool:
    """
    Refresh cookie ``Secure`` flag.

    If ``AGENT_COOKIE_SECURE`` is unset, derive from HTTPS: ``request.url.scheme`` or
    ``X-Forwarded-Proto`` (reverse proxy). Set env ``true``/``false`` to force when needed.
    """
    raw = (os.environ.get("AGENT_COOKIE_SECURE") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    if (request.url.scheme or "").lower() == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return proto == "https"


def _bearer_user_role_from_request(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    token = auth.removeprefix("Bearer ").strip()
    if not token:
        return None
    user = get_user_for_bearer_token(token)
    return user.role.lower() if user else None


from apps.backend.infrastructure.cron import start_cron_scheduler, stop_cron_scheduler
from apps.backend.infrastructure.scheduler import start_scheduler_worker, stop_scheduler_worker
from apps.backend.infrastructure.scheduler_jobs_runner import (
    start_scheduler_jobs_worker,
    stop_scheduler_jobs_worker,
)
from apps.backend.infrastructure.project_runs_runner import (
    start_project_runs_worker,
    stop_project_runs_worker,
)
from apps.backend.integrations import discord_bridge, telegram_bridge

# Optional out-of-band gateways (Telegram, Discord, …). New bridges: start/stop here like below;
# implementation guide: apps/backend/integrations/bridges/README.md


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # After uvicorn's logging dictConfig, httpx/httpcore levels must be re-applied (see log_redaction).
    apply_http_client_log_levels()
    db.init_pool()
    try:
        setup_admin_claim_if_needed()
    except Exception:
        logger.exception(
            "First-admin bootstrap failed (DB migrations? or set AGENT_INITIAL_ADMIN_EMAIL/PASSWORD)"
        )
    if (os.environ.get("AGENT_CORS_ORIGINS") or "*").strip() == "*":
        logger.warning(
            "AGENT_CORS_ORIGINS is '*'. For a public host, set explicit origins "
            "(e.g. https://openwebui.example) so browsers do not send creds to arbitrary sites."
        )
    get_registry()
    try:
        from apps.backend.infrastructure.rag_embedding_sync import ensure_rag_embedding_aligned

        await asyncio.to_thread(ensure_rag_embedding_aligned, log_prefix="startup")
    except Exception:
        logger.exception("RAG embedding provider sync failed")
    try:
        await asyncio.to_thread(run_startup_rag_docs_ingest)
    except Exception:
        logger.exception("RAG docs startup ingest failed (embedding backend unreachable?)")
    
    # Deferred code index on startup - REMOVED
    # Workspace is now per-user from DB, not hardcoded. Indexing happens per-workspace on demand.
    
    start_cron_scheduler()
    try:
        start_scheduler_worker()
    except Exception:
        logger.exception("Scheduler worker failed to start (optional)")
    try:
        start_scheduler_jobs_worker()
    except Exception:
        logger.exception("Scheduler jobs server worker failed to start (optional)")
    try:
        start_project_runs_worker()
    except Exception:
        logger.exception("Project runs worker failed to start (optional)")
    try:
        discord_bridge.start_background()
    except Exception:
        logger.exception("Discord bridge failed to start (optional)")
    try:
        telegram_bridge.start_background()
    except Exception:
        logger.exception("Telegram bridge failed to start (optional)")
    if is_first_start():
        # Let bridge/cron idle lines flush before the setup token block (last visible line).
        await asyncio.sleep(0.75)
    emit_initial_setup_notice_at_end()
    yield
    try:
        discord_bridge.stop_background()
    except Exception:
        pass
    try:
        telegram_bridge.stop_background()
    except Exception:
        pass
    stop_cron_scheduler()
    try:
        stop_scheduler_worker()
    except Exception:
        pass
    try:
        stop_scheduler_jobs_worker()
    except Exception:
        pass
    try:
        stop_project_runs_worker()
    except Exception:
        pass
    db.close_pool()


app = FastAPI(title="agent-layer", version="0.7.7", lifespan=lifespan)
app.include_router(user_secrets_router)
app.include_router(conversations_router)
app.include_router(dashboard_router)
app.include_router(user_data_router)
app.include_router(memory_router)
app.include_router(tools_router)
app.include_router(rag_router)
app.include_router(codebase_router)
app.include_router(chat_ws_router)
app.include_router(studio_router)
#app.include_router(pidea_router)
app.include_router(scheduler_jobs_admin_router)
app.include_router(scheduler_job_presets_router)
app.include_router(scheduler_jobs_user_router)
app.include_router(scheduler_job_runs_user_router)
app.include_router(scheduler_job_runs_admin_router)
app.include_router(scheduler_job_presets_user_router)
app.include_router(project_runs_router)
app.include_router(agents_router)
app.include_router(session_runtime_router)
app.include_router(friends_router)
app.include_router(shares_router)
app.include_router(workspaces_router)


# Auth Endpoints
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


@app.post("/auth/login")
async def login(request: Request, login_data: LoginRequest):
    user = get_user_by_email(login_data.email)
    if not user or not user.password_hash or not verify_password(login_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return _auth_session_response(request, user)


@app.post("/auth/refresh")
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


@app.post("/auth/logout")
async def auth_logout(request: Request):
    raw = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw:
        revoke_refresh_token(raw)
    response = JSONResponse(content={"ok": True})
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/")
    return response


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


@app.get("/auth/setup-status")
async def auth_setup_status():
    """Initial instance configuration state (admin account, LLM catalog)."""
    return build_setup_status()


@app.post("/auth/setup")
async def auth_setup(request: Request, body: AuthSetupBody):
    """Create the first administrator (only while no admin exists)."""
    enforce_setup_rate_limit(request)
    validate_setup_token(body.setup_token)
    validate_setup_email(body.email)
    validate_setup_password(body.password, body.password_confirm)
    user = create_first_admin(email=body.email, password=body.password)
    return _auth_session_response(request, user)


@app.post("/auth/setup/llm")
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


@app.get("/auth/setup/catalog")
async def auth_setup_catalog(request: Request):
    """Provider reachability and chat/embedding model lists for setup step 2."""
    await require_admin(request)
    return build_setup_catalog()


class AuthSetupPreferencesBody(SetupPreferencesBody):
    """Alias for OpenAPI; fields defined on SetupPreferencesBody."""


@app.post("/auth/setup/preferences")
async def auth_setup_preferences(request: Request, body: AuthSetupPreferencesBody):
    """Persist preferred provider and profile models (general, coding, embedding)."""
    await require_admin(request)
    return apply_setup_preferences(body)


class AuthSetupTestEmbeddingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(..., min_length=1, max_length=256)


@app.post("/auth/setup/test-embedding")
async def auth_setup_test_embedding(request: Request, body: AuthSetupTestEmbeddingBody):
    """Probe embedding dimension for a model id on the configured embedding API."""
    await require_admin(request)
    return await test_embedding_model(body.model)


@app.post("/auth/setup/skip-profiles")
async def auth_setup_skip_profiles(request: Request):
    """Skip provider wizard step; persist catalog suggestions when a chat provider is reachable."""
    await require_admin(request)
    return apply_setup_skip_suggestions()


@app.get("/auth/me")
async def get_current_user_info(request: Request):
    """
    Current session user. Implemented without ``require_permission`` so FastAPI does not treat a
    bare ``user`` parameter as request-body injection (that caused 422).
    """
    user = await get_current_user(request)
    discord_uid = db.user_discord_user_id_get(user.id)
    telegram_uid = db.user_telegram_user_id_get(user.id)
    base = {
        "id": str(user.id),
        "email": user.email,
        "role": user.role,
        "created_at": user.created_at.isoformat(),
        "discord_user_id": discord_uid,
        "telegram_user_id": telegram_uid,
    }
    if user.role != "admin":
        id_token = set_identity(1, user.id)
        try:
            return base
        finally:
            reset_identity(id_token)
    return base


@app.get("/v1/admin/operator-settings")
async def get_operator_settings(request: Request):
    await require_admin(request)
    return operator_settings_public()


@app.put("/v1/admin/operator-settings")
async def put_operator_settings(request: Request, body: OperatorSettingsPayload):
    await require_admin(request)
    operator_settings_apply(body)
    return operator_settings_public()


@app.patch("/v1/admin/operator-settings")
async def patch_operator_settings(request: Request, body: OperatorSettingsPatch):
    await require_admin(request)
    apply_operator_settings_patch(body)
    return operator_settings_public()


class ExternalLlmModelsBody(BaseModel):
    """Optional form overrides; omitted fields use first endpoint or legacy operator_settings."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    api_key: str | None = None
    endpoint_id: int | None = Field(
        default=None,
        description="Use this endpoint's URL+key when base_url/api_key not sent.",
    )


class ExternalLlmEndpointItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    sort_order: int = 0
    enabled: bool = True
    label: str = ""
    base_url: str = ""
    api_key: str | None = None
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None


class ExternalLlmEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[ExternalLlmEndpointItem] = Field(default_factory=list)


@app.get("/v1/admin/external-llm/endpoints")
async def admin_get_external_llm_endpoints(request: Request):
    """List external OpenAI-compatible endpoints (keys redacted)."""
    await require_admin(request)
    out: list[dict[str, Any]] = []
    for r in db.external_llm_endpoints_list_all():
        k = str(r.get("api_key") or "")
        out.append(
            {
                "id": r["id"],
                "sort_order": r["sort_order"],
                "enabled": r["enabled"],
                "label": r.get("label") or "",
                "base_url": r.get("base_url") or "",
                "api_key_configured": bool(k.strip()),
                "api_key_last4": (k[-4:] if len(k) >= 4 else None),
                "model_default": r.get("model_default"),
                "model_vlm": r.get("model_vlm"),
                "model_agent": r.get("model_agent"),
                "model_coding": r.get("model_coding"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
        )
    return {"endpoints": out}


@app.put("/v1/admin/external-llm/endpoints")
async def admin_put_external_llm_endpoints(request: Request, body: ExternalLlmEndpointsPutBody):
    """Replace/sync external LLM endpoints (multi-provider, multi-key failover order = sort_order)."""
    await require_admin(request)
    raw = [e.model_dump() for e in body.endpoints]
    try:
        db.external_llm_endpoints_sync(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    invalidate_operator_settings_cache()
    from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

    invalidate_model_catalog_cache()
    return await admin_get_external_llm_endpoints(request)


@app.post("/v1/admin/external-llm/models")
async def admin_external_llm_models(request: Request, body: ExternalLlmModelsBody = ExternalLlmModelsBody()):
    """
    List models from the configured external OpenAI-compatible API (``GET {base}/v1/models``).

    Uses non-empty ``base_url`` / ``api_key`` from the body when provided; otherwise the first
    enabled row in ``operator_external_llm_endpoints`` (or ``endpoint_id`` when set).
    """
    await require_admin(request)
    try:
        bu, key = resolve_external_llm_credentials_for_catalog(
            body.base_url, body.api_key, endpoint_id=body.endpoint_id
        )
    except ValueError as e:
        tag = str(e)
        if tag == "missing_base_url":
            raise HTTPException(
                status_code=400,
                detail="Base URL fehlt (im Formular eintragen oder zuerst speichern).",
            ) from e
        if tag == "missing_api_key":
            raise HTTPException(
                status_code=400,
                detail="API-Key fehlt (einmalig eintragen oder zuerst speichern).",
            ) from e
        if tag == "unknown_endpoint":
            raise HTTPException(status_code=400, detail="Unbekannter endpoint_id.") from e
        if tag == "no_external_endpoint":
            raise HTTPException(
                status_code=400,
                detail="Kein externer LLM-Endpunkt konfiguriert (Admin → External LLM Endpoints).",
            ) from e
        raise
    url = external_models_list_url(bu)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=external_api_headers(bu, key),
                timeout=httpx.Timeout(45.0),
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Verbindung fehlgeschlagen: {e}") from e
    if resp.status_code != 200:
        snippet = (resp.text or "").strip()[:4000]
        raise HTTPException(
            status_code=min(resp.status_code, 599),
            detail=snippet or f"HTTP {resp.status_code}",
        )
    try:
        return resp.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="Antwort der API war kein JSON.") from e


@app.get("/v1/admin/interfaces")
async def get_interface_hints(request: Request):
    await require_admin(request)
    return interface_hints_public()


@app.put("/v1/admin/interfaces")
async def put_interface_hints(request: Request, body: InterfaceHintsPayload):
    await require_admin(request)
    apply_interface_hints(body)
    return interface_hints_public()


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


@app.get("/v1/admin/tenants")
async def admin_list_tenants(request: Request):
    """List tenants (``tenants.id`` = value for tool allowlists and ``users.tenant_id``)."""
    await require_admin(request)
    return {"tenants": db.tenants_list()}


@app.post("/v1/admin/tenants")
async def admin_create_tenant(request: Request, body: AdminCreateTenantBody):
    """Create a tenant (e.g. work / friends). Admin only."""
    await require_admin(request)
    row = db.tenant_insert(body.name)
    return {"ok": True, "tenant": row}


@app.get("/v1/admin/users")
async def admin_list_users(request: Request):
    """List all users (admin UI); ``email`` may be empty when the row has no mailbox."""
    await require_admin(request)
    return {"users": list_all_users()}


@app.patch("/v1/admin/users/{user_id}")
async def admin_patch_user(request: Request, user_id: uuid.UUID, body: AdminPatchUserBody):
    """Update ``tenant_id``, ``workspace_quota``, ``workspace_self_allowed``. Admin only."""
    await require_admin(request)
    if body.tenant_id is None and body.workspace_quota is None and body.workspace_self_allowed is None:
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

    return {
        "ok": True,
        "id": str(user_id),
        "tenant_id": db.user_tenant_id(user_id),
    }


@app.post("/v1/admin/users")
async def admin_create_user(request: Request, body: AdminCreateUserBody):
    """Create a password user (e.g. role ``user``). Admin only."""
    await require_admin(request)
    if not db.tenant_exists(body.tenant_id):
        raise HTTPException(status_code=400, detail="unknown tenant_id")
    if get_user_by_email(body.email):
        raise HTTPException(status_code=409, detail="email already registered")
    u = create_user(body.email, body.password, body.role, tenant_id=body.tenant_id)
    return {"ok": True, "id": str(u.id), "email": u.email, "role": u.role, "tenant_id": body.tenant_id}


@app.get("/auth/policy")
def http_auth_policy():
    """Public JSON: path classes, middleware auth behavior, admin routes."""
    return public_http_auth_policy()


# Legacy control UI (optional): repo ``interfaces/web/static`` if present.
_repo_root = Path(__file__).resolve().parents[3]
_control_dir = _repo_root / "interfaces" / "web" / "static"
_control_login_html = _control_dir / "login.html"
_js_dir = _control_dir / "js"
if _js_dir.is_dir():
    app.mount("/js", StaticFiles(directory=str(_js_dir)), name="public_js")

_agent_ui_dir = _repo_root / "apps" / "frontend" / "dist"
_agent_index = _agent_ui_dir / "index.html"
if _agent_index.is_file():

    @app.get("/coding-agent")
    async def redirect_legacy_coding_agent(request: Request):
        """Legacy deep links used /coding-agent; SPA lives under /app/coding-agent."""
        q = request.url.query
        target = "/app/coding-agent" + (f"?{q}" if q else "")
        return RedirectResponse(url=target, status_code=302)

    @app.get("/app")
    async def agent_ui_spa_root():
        """``/app`` without trailing slash: same shell as ``/app/`` (hard refresh must not 405)."""
        return FileResponse(_agent_index)

    @app.get("/app/chat")
    @app.get("/app/coding-agent")
    @app.get("/app/dashboard")
    @app.get("/app/docs")
    @app.get("/app/login")
    @app.get("/app/setup")
    @app.get("/app/schedules")
    @app.get("/app/settings")
    @app.get("/app/settings/profile")
    @app.get("/app/settings/connections")
    @app.get("/app/settings/tools")
    @app.get("/app/settings/agent")
    @app.get("/app/settings/friends")
    @app.get("/app/settings/shares")
    @app.get("/app/studio")
    @app.get("/app/admin")
    @app.get("/app/admin/interfaces")
    @app.get("/app/admin/tools")
    @app.get("/app/admin/users")
    @app.get("/app/admin/scheduled-jobs")
    @app.get("/app/admin/schedules")
    @app.get("/app/admin/workflows")
    async def agent_ui_spa_shell():
        """Serve SPA index for client-side routes (must register before mount /app)."""
        return FileResponse(_agent_index)

    app.mount(
        "/app",
        StaticFiles(directory=str(_agent_ui_dir), html=True),
        name="agent_ui",
    )

_cors_origins = [
    o.strip() for o in os.environ.get("AGENT_CORS_ORIGINS", "*").split(",") if o.strip()
]
_cors_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # CORS preflight must not require Bearer auth (browser sends no Authorization).
    if (request.method or "").upper() == "OPTIONS":
        return await call_next(request)

    # See apps/backend/api/optional_http_access.py and GET /auth/policy
    if middleware_path_is_public(path, request.method):
        return await call_next(request)

    # Handlers resolve Bearer (JWT / API key) themselves; see public_http_auth_policy
    if is_identity_deferred_route(path, request.method):
        return await call_next(request)

    # All other endpoints require valid auth
    try:
        await get_current_user(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    return await call_next(request)


@app.get("/")
def root(request: Request):
    """JSON index for API clients; top-level browser navigations go to the SPA (see /auth/policy for JSON)."""
    accept = (request.headers.get("accept") or "").lower()
    sec_dest = (request.headers.get("sec-fetch-dest") or "").lower()
    first = accept.split(",")[0].strip() if accept else ""
    wants_html = sec_dest == "document" or (
        "text/html" in accept and not first.startswith("application/json")
    )
    if wants_html and _agent_index.is_file():
        return RedirectResponse(url="/app/", status_code=302)

    out: dict[str, object] = {
        "service": "agent-layer",
        "first_party_ui": "/app/",
        "login": "/login",
        "hint": "OpenAI API under /v1/ (e.g. POST /v1/chat/completions); WebSocket /ws/v1/chat; GET /health; GET /v1/tools",
    }
    if _agent_index.is_file():
        out["operator_admin_ui"] = "/app/admin"
    return out


@app.get("/favicon.ico")
def favicon():
    """Empty favicon so GET does not fall through to POST /{tool_name} (would return 405)."""
    return Response(status_code=204)


@app.get("/login")
def login_page():
    """Browser login: legacy ``interfaces/web/static/login.html`` if present, else SPA."""
    if _control_login_html.is_file():
        return FileResponse(_control_login_html)
    if _agent_index.is_file():
        return RedirectResponse(url="/app/login", status_code=307)
    raise HTTPException(status_code=404, detail="login UI not shipped")


@app.get("/chat")
def browser_chat_entry():
    """Short URL → SPA (public: loading the shell must not require JWT)."""
    return RedirectResponse(url="/app/chat", status_code=307)


@app.get("/dashboard")
def browser_dashboard_entry():
    """Short URL → first-party app home (`/app/`)."""
    return RedirectResponse(url="/app/", status_code=307)


@app.get("/health")
def health():
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.commit()
    except Exception:
        logger.exception("database health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "down"},
        )
    return {"status": "ok", "database": "ok"}


def merge_model_catalog_rows(
    ollama_rows: list[dict[str, Any]],
    llama_cpp_rows: list[dict[str, Any]],
    *more: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-export: dedupe by ``(owned_by, id)``; same id on different providers stays separate."""
    from apps.backend.infrastructure.model_catalog_providers import merge_model_catalog_rows as _merge

    return _merge(ollama_rows, llama_cpp_rows, *more)


@app.get("/v1/models")
async def models_proxy():
    """
    OpenAI-style model list: all catalog providers (Ollama, llama.cpp, each external LLM endpoint).

    One provider failing does not remove rows from others. ``agentlayer`` keys match row ``owned_by``.
    """
    from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog

    merged, agentlayer = await asyncio.to_thread(fetch_full_model_catalog)
    return {"object": "list", "data": merged, "agentlayer": agentlayer}


def _completion_to_sse_lines(completion: dict[str, Any]) -> bytes:
    """Build OpenAI-style SSE body from a full chat.completion JSON (Open WebUI sends stream=true)."""
    cid = completion.get("id") or f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = completion.get("created")
    if not isinstance(created, int):
        created = int(time.time())
    model = completion.get("model") or ""
    choice0 = (completion.get("choices") or [{}])[0]
    msg = choice0.get("message") if isinstance(choice0.get("message"), dict) else {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)
    finish = choice0.get("finish_reason") or "stop"
    base = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
    }
    lines: list[bytes] = []
    lines.append(
        (
            "data: "
            + json.dumps(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"role": "assistant", "content": content},
                            "finish_reason": None,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode()
    )
    lines.append(
        (
            "data: "
            + json.dumps(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": finish,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        ).encode()
    )
    lines.append(b"data: [DONE]\n\n")
    return b"".join(lines)


def _generate_openapi_spec(title: str, tool_filter=None):
    reg = get_registry()
    
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": title,
            "version": "0.7.0"
        },
        "paths": {},
        "components": {
            "schemas": {}
        }
    }
    
    for tool_spec in reg.chat_tool_specs:
        fn = tool_spec.get("function", {})
        name = fn.get("name")
        if not name:
            continue
            
        if tool_filter and name not in tool_filter:
            continue
            
        description = fn.get("TOOL_DESCRIPTION", fn.get("description", ""))
        parameters = fn.get("parameters", {})
        
        spec["paths"][f"/{name}"] = {
            "post": {
                "summary": description,
                "operationId": name,
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": parameters
                        }
                    }
                },
                "responses": {
                    "200": {
                        "description": "Tool execution result",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "result": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    return spec


@app.get("/openapi.json")
async def openapi_spec_all():
    """OpenAPI 3.0 Specification (all tools)"""
    return _generate_openapi_spec("Jetpack Agent Layer All Tools")


@app.get("/openapi/{domain}/openapi.json")
async def openapi_spec_domain(domain: str):
    """OpenAPI 3.0 Specification filtered by tool domain"""
    reg = get_registry()
    domain_tools = []
    
    for meta in reg.tools_meta:
        if meta.get("domain") == domain:
            domain_tools.extend(meta.get("tools", []))
    
    if not domain_tools:
        raise HTTPException(status_code=404, detail="domain not found")
        
    return _generate_openapi_spec(f"Jetpack Agent: {domain}", tool_filter=domain_tools)


@app.get("/openapi/{domain}.json")
async def openapi_spec_domain_legacy(domain: str):
    return await openapi_spec_domain(domain)


@app.get("/openapi/tool/{tool_name}/openapi.json")
async def openapi_spec_single_tool(tool_name: str):
    """OpenAPI 3.0 Specification for a single individual tool"""
    return _generate_openapi_spec(f"Jetpack Agent: {tool_name}", tool_filter=[tool_name])


@app.get("/openapi/domains")
async def list_openapi_domains():
    """List available tool domains for separate OpenAPI endpoints"""
    reg = get_registry()
    domains = {}
    
    for meta in reg.tools_meta:
        domain = meta.get("domain")
        if domain:
            if domain not in domains:
                domains[domain] = []
            domains[domain].extend(meta.get("tools", []))
    
    result = []
    for domain, tools in domains.items():
        result.append({
            "domain": domain,
            "tool_count": len(tools),
            "openapi_url": f"/openapi/{domain}.json"
        })
    
    return {"domains": result}


def _merge_capability_confirm(request: Request, body_confirm: Any) -> frozenset[str]:
    """Header X-Agent-Capability-Confirm (comma) ∪ JSON ``agent_capability_confirm`` (body route only)."""
    raw = (request.headers.get("X-Agent-Capability-Confirm") or "").strip()
    hdr: frozenset[str] = frozenset()
    if raw:
        hdr = frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return hdr | parse_user_capability_confirm(body_confirm)


@app.post("/{tool_name}")
async def run_tool_direct(tool_name: str, request: Request):
    """Direct tool execution endpoint (Open WebUI calls this directly per tool)"""
    try:
        arguments = await request.json()
    except Exception:
        arguments = {}
    
    from apps.backend.domain.plugin_system.tools import run_tool
    
    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)
    _cf_tok = bind_capability_confirmed(_merge_capability_confirm(request, None))

    try:
        result = run_tool(tool_name, arguments)
        return {
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Direct tool execution failed for {tool_name}")
        raise HTTPException(status_code=500, detail=http_500_detail(e))
    finally:
        reset_capability_confirmed(_cf_tok)
        reset_identity(id_token)


@app.post("/tools/run")
async def run_tool_openwebui(request: Request):
    """Generic tool execution endpoint for Open WebUI Tool Server"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")
    
    tool_name = body.get("name")
    arguments = body.get("arguments", {})
    body_confirm = body.get("agent_capability_confirm")

    if not tool_name:
        raise HTTPException(status_code=400, detail="missing tool name")
    
    from apps.backend.domain.plugin_system.tools import run_tool
    
    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)
    _cf_tok = bind_capability_confirmed(_merge_capability_confirm(request, body_confirm))

    try:
        result = run_tool(tool_name, arguments)
        return {
            "result": result
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Open WebUI tool execution failed for {tool_name}")
        raise HTTPException(status_code=500, detail=http_500_detail(e))
    finally:
        reset_capability_confirmed(_cf_tok)
        reset_identity(id_token)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    want_stream = bool(body.get("stream"))
    work = dict(body)
    work["stream"] = False

    user_id, tenant_id = resolve_chat_identity(request)
    id_token = set_identity(tenant_id, user_id)

    router_hdr = (request.headers.get("X-Agent-Router-Categories") or "").strip() or None
    tool_dom_hdr = (request.headers.get("X-Agent-Tool-Domain") or "").strip() or None
    model_prof = (request.headers.get("X-Agent-Model-Profile") or "").strip() or None
    model_ovr = (request.headers.get("X-Agent-Model-Override") or "").strip() or None

    try:
        result = await chat_completion(
            work,
            router_categories_header=router_hdr,
            tool_domain_header=tool_dom_hdr,
            model_profile_header=model_prof,
            model_override_header=model_ovr,
            bearer_user_role=_bearer_user_role_from_request(request),
            stream_requested=want_stream,
        )
    except WorkspaceAccessDenied as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        detail, log_exc = user_visible_llm_transport_error(e)
        if log_exc:
            logger.exception("chat completion failed")
        else:
            logger.warning("chat completion failed: %s (%s)", detail, e)
        raise HTTPException(status_code=502, detail=detail) from e
    finally:
        reset_identity(id_token)

    if want_stream:
        if inspect.isasyncgen(result):
            return StreamingResponse(
                result,
                media_type="text/event-stream",
            )
        return StreamingResponse(
            iter([_completion_to_sse_lines(result)]),
            media_type="text/event-stream",
        )

    return result