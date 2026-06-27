"""OpenAI-compatible HTTP API: catalog LLM providers and local tools."""

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
    normalize_external_llm_base_url,
)
from apps.backend.infrastructure.llm_env_providers import parse_llm_env_providers
from apps.backend.infrastructure.embedding_env_providers import parse_embedding_env_providers
from apps.backend.infrastructure.extractor_env_providers import parse_extractor_env_providers
from apps.backend.infrastructure.voice_env_providers import (
    parse_voice_stt_env_providers,
    parse_voice_tts_env_providers,
)
from apps.backend.api.optional_http_access import (
    is_identity_deferred_route,
    is_media_stream_route,
    is_dashboard_public_share_route,
    middleware_path_is_public,
    public_http_auth_policy,
)
from apps.backend.domain.admin_setup import is_first_start
from apps.backend.infrastructure import smart_route_service as _smart_route_service  # noqa: F401
from apps.backend.infrastructure.instance_setup_service import (
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
from apps.backend.infrastructure.setup_catalog_service import (
    SetupPreferencesBody,
    apply_setup_preferences,
    apply_enable_chat_provider_embedding,
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
from apps.backend.api.message_feedback_api import admin_router as message_feedback_admin_router
from apps.backend.api.message_feedback_api import router as message_feedback_router
from apps.backend.api.notifications_api import router as notifications_router
from apps.backend.infrastructure.delegate_api import router as delegate_router
from apps.backend.infrastructure.memory_api import router as memory_router
from apps.backend.infrastructure.user_secrets_api import router as user_secrets_router
from apps.backend.api.conversations_api import router as conversations_router
from apps.backend.dashboard.router import router as dashboard_router
from apps.backend.media.router import router as media_router
from apps.backend.api.voice_api import router as voice_router
from apps.backend.api.voice_realtime_websocket import router as voice_realtime_ws_router
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
from apps.backend.api.task_artifacts_api import router as task_artifacts_router
from apps.backend.api.tasks_api import router as tasks_router
from apps.backend.api.run_traces_admin_api import router as run_traces_admin_router
from apps.backend.api.benchmarks_admin_api import router as benchmarks_admin_router
from apps.backend.api.agent_config_admin_api import router as agent_config_admin_router
from apps.backend.api.benchmark_harness_admin_api import router as benchmark_harness_admin_router
from apps.backend.api.friends_api import router as friends_router
from apps.backend.api.shares_api import router as shares_router
from apps.backend.api.workspaces_api import router as workspaces_router
from apps.backend.api.workspaces_admin_api import router as workspaces_admin_router
from apps.backend.api.github_api import router as github_router
from apps.backend.api.agents_api import router as agents_router
from apps.backend.api.agents_admin_api import router as agents_admin_router
from apps.backend.api.agents_import_admin_api import router as agents_import_admin_router
from apps.backend.api.tools_admin_api import router as tools_admin_router
from apps.backend.api.tools_import_admin_api import router as tools_import_admin_router
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
from apps.backend.infrastructure.agent_tasks_runner import (
    start_agent_tasks_worker,
    stop_agent_tasks_worker,
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
        from apps.backend.infrastructure.benchmark_runs_store import (
            reconcile_orphaned_runs_on_startup,
        )

        n = reconcile_orphaned_runs_on_startup()
        if n:
            logger.warning("Marked %s orphaned benchmark run(s) as failed after startup", n)
    except Exception:
        logger.exception("Benchmark orphan reconciliation failed")
    try:
        from apps.backend.infrastructure.agent_runs_store import (
            reconcile_orphaned_agent_runs_on_startup,
        )

        n_agent = reconcile_orphaned_agent_runs_on_startup()
        if n_agent:
            logger.warning("Marked %s orphaned agent run(s) as failed after startup", n_agent)
    except Exception:
        logger.exception("Agent run orphan reconciliation failed")
    try:
        setup_admin_claim_if_needed()
    except Exception:
        logger.exception(
            "First-admin bootstrap failed (DB migrations? or set AGENT_INITIAL_ADMIN_EMAIL/PASSWORD)"
        )
    cors_env = os.environ.get("AGENT_CORS_ORIGINS", "").strip()
    # Security check: prevent CORS wildcard
    if cors_env == "*":
        raise ValueError(
            "SECURITY: CORS_ALLOW_ORIGINS must not be set to '*' in production! "
            "Set specific origins instead."
        )
    if not cors_env:
        logger.warning(
            "CORS is not explicitly configured (AGENT_CORS_ORIGINS not set). "
            "In production, set AGENT_CORS_ORIGINS to specific origins "
            "(e.g. https://openwebui.example) to prevent wildcard CORS. "
            "Without it, browsers will block credentials."
        )
    get_registry()

    async def _startup_rag_background() -> None:
        try:
            from apps.backend.infrastructure.rag_embedding_sync import ensure_rag_embedding_aligned

            await asyncio.to_thread(ensure_rag_embedding_aligned, log_prefix="startup")
        except Exception:
            logger.exception("RAG embedding provider sync failed")
        skip_docs = (os.environ.get("AGENT_SKIP_STARTUP_RAG_DOCS_INGEST") or "").strip().lower()
        if skip_docs in ("1", "true", "yes"):
            return
        try:
            await asyncio.to_thread(run_startup_rag_docs_ingest)
        except Exception:
            logger.exception("RAG docs startup ingest failed (embedding backend unreachable?)")

    asyncio.create_task(_startup_rag_background())
    logger.info(
        "RAG embedding sync + docs ingest scheduled in background (API/UI ready immediately)"
    )
    
    # Deferred code index on startup - REMOVED
    # Workspace is now per-user from DB, not hardcoded. Indexing happens per-workspace on demand.
    
    start_cron_scheduler()
    try:
        from apps.backend.infrastructure.workspace_reindex_scheduler import (
            start_workspace_reindex_scheduler,
        )

        start_workspace_reindex_scheduler()
    except Exception:
        logger.exception("Workspace reindex scheduler failed to start (optional)")
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
        start_agent_tasks_worker()
    except Exception:
        logger.exception("Agent tasks worker failed to start (optional)")
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
        from apps.backend.infrastructure.benchmark_runner import cancel_all_active_benchmark_runs

        n_cancelled = cancel_all_active_benchmark_runs()
        if n_cancelled:
            logger.info(
                "Signalled cancel for %s active benchmark run(s) before shutdown",
                n_cancelled,
            )
            await asyncio.sleep(0.5)
    except Exception:
        logger.debug("benchmark shutdown cancel skipped", exc_info=True)
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
        from apps.backend.infrastructure.workspace_reindex_scheduler import (
            stop_workspace_reindex_scheduler,
        )

        stop_workspace_reindex_scheduler()
    except Exception:
        pass
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
    try:
        stop_agent_tasks_worker()
    except Exception:
        pass
    db.close_pool()


app = FastAPI(title="agent-layer", version="0.7.7", lifespan=lifespan)
app.include_router(user_secrets_router)
app.include_router(conversations_router)
app.include_router(message_feedback_router)
app.include_router(message_feedback_admin_router)
app.include_router(dashboard_router)
app.include_router(media_router)
app.include_router(voice_router)
app.include_router(voice_realtime_ws_router)
app.include_router(user_data_router)
app.include_router(notifications_router)
app.include_router(delegate_router)
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
app.include_router(tasks_router)
app.include_router(task_artifacts_router)
app.include_router(run_traces_admin_router)
app.include_router(benchmarks_admin_router)
app.include_router(agent_config_admin_router)
app.include_router(benchmark_harness_admin_router)
app.include_router(agents_router)
app.include_router(agents_admin_router)
app.include_router(agents_import_admin_router)
app.include_router(tools_admin_router)
app.include_router(tools_import_admin_router)
app.include_router(session_runtime_router)
app.include_router(friends_router)
app.include_router(shares_router)
app.include_router(workspaces_router)
app.include_router(workspaces_admin_router)
app.include_router(github_router)


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


@app.post("/auth/setup/enable-chat-provider-embedding")
async def auth_setup_enable_chat_provider_embedding(request: Request):
    """Opt-in: use chat provider host for embeddings (operator_settings)."""
    await require_admin(request)
    return apply_enable_chat_provider_embedding()


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
    api_header_name: str | None = Field(
        default=None,
        description="HTTP header for api_key (Authorization, X-API-KEY, …). Default Authorization.",
    )
    model_default: str | None = None
    model_vlm: str | None = None
    model_agent: str | None = None
    model_coding: str | None = None
    max_parallel: int = Field(default=1, ge=1, le=64)


class ExternalLlmEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[ExternalLlmEndpointItem] = Field(default_factory=list)


class EnvLlmProvidersImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_indexes: list[int] | None = Field(
        default=None,
        description="Env provider slots to import. Omit/null imports all detected slots.",
    )


class ModelCatalogPrefItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    visible_in_chat: bool = True
    profile_tags: list[str] = Field(default_factory=list)
    sort_order: int = 0


class ModelCatalogPrefsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prefs: list[ModelCatalogPrefItem] = Field(default_factory=list)


class ModelAccessPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)
    access_state: Literal["inherit", "allow", "deny"] = "inherit"
    sort_order: int = 0


class ModelDefaultPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Literal["default", "agent", "coding", "vlm", "embedding", "extractor", "stt", "tts"]
    provider_id: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=512)


class ProviderCapabilityPolicyItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability: Literal["chat", "embedding", "extractor", "stt", "tts", "voice_realtime"]
    provider_id: str = Field(min_length=1, max_length=64)
    access_state: Literal["inherit", "allow", "deny"] = "inherit"


class ModelAccessPoliciesPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_access: list[ModelAccessPolicyItem] = Field(default_factory=list)
    model_defaults: list[ModelDefaultPolicyItem] = Field(default_factory=list)
    provider_capabilities: list[ProviderCapabilityPolicyItem] = Field(default_factory=list)


class OperatorProviderEndpointItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    sort_order: int = 0
    enabled: bool = True
    label: str = ""
    base_url: str = ""
    api_key: str | None = None
    api_header_name: str | None = None
    model_default: str | None = None
    max_parallel: int = Field(default=1, ge=1, le=64)
    options_json: dict[str, Any] = Field(default_factory=dict)


class OperatorProviderEndpointsPutBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoints: list[OperatorProviderEndpointItem] = Field(default_factory=list)
    delete_endpoint_ids: list[int] = Field(default_factory=list)


def _operator_provider_kind_or_404(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in _operator_provider_endpoint_kinds():
        raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")
    return k


def _operator_endpoint_provider_id(kind: str, endpoint_id: int) -> str:
    if kind == "chat":
        return f"provider_db_{int(endpoint_id)}"
    return f"{kind}_provider_db_{int(endpoint_id)}"


def _operator_provider_endpoint_kinds() -> tuple[str, ...]:
    return ("chat", "embedding", "extractor", "voice_stt", "voice_tts")


def _operator_provider_endpoint_metadata() -> tuple[dict[str, Any], ...]:
    return (
        {
            "kind": "chat",
            "capability": "chat",
            "title_i18n_key": "modelAccessChatTitle",
            "intro_i18n_key": "modelAccessChatIntro",
            "empty_i18n_key": "modelAccessChatEmpty",
            "model_label_i18n_key": "ifMemModelId",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "chat_model",
            "env_prefix_pattern": "LLM_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "embedding",
            "capability": "embedding",
            "title_i18n_key": "modelAccessEmbeddingTitle",
            "intro_i18n_key": "modelAccessEmbeddingIntro",
            "empty_i18n_key": "modelAccessEmbeddingEmpty",
            "model_label_i18n_key": "ifMemModelId",
            "model_placeholder_i18n_key": "ifMemoryModelFilePlaceholder",
            "model_setting_key": "rag_embedding_model",
            "env_prefix_pattern": "EMBEDDING_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "extractor",
            "capability": "extractor",
            "title_i18n_key": "modelAccessExtractorTitle",
            "intro_i18n_key": "modelAccessExtractorIntro",
            "empty_i18n_key": "modelAccessExtractorEmpty",
            "model_label_i18n_key": "ifMemExtractorModel",
            "model_placeholder_i18n_key": "ifMemExtractorModelPlaceholder",
            "model_setting_key": "extractor_model",
            "env_prefix_pattern": "EXTRACTOR_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "voice_stt",
            "capability": "stt",
            "title_i18n_key": "modelAccessSttTitle",
            "intro_i18n_key": "modelAccessSttIntro",
            "empty_i18n_key": "modelAccessSttEmpty",
            "model_label_i18n_key": "ifPlatformVoiceSttModel",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "voice_stt_model",
            "env_prefix_pattern": "VOICE_STT_PROVIDER_N_*",
            "supports_models": True,
        },
        {
            "kind": "voice_tts",
            "capability": "tts",
            "title_i18n_key": "modelAccessTtsTitle",
            "intro_i18n_key": "modelAccessTtsIntro",
            "empty_i18n_key": "modelAccessTtsEmpty",
            "model_label_i18n_key": "ifPlatformVoiceTtsModel",
            "model_placeholder_i18n_key": "ifLlmSelectProviderModel",
            "model_setting_key": "voice_tts_model",
            "env_prefix_pattern": "VOICE_TTS_PROVIDER_N_*",
            "supports_models": True,
        },
    )


def _model_default_profile_metadata() -> tuple[dict[str, Any], ...]:
    return (
        {
            "profile": "default",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_default",
            "source": "catalog",
        },
        {
            "profile": "agent",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_agent",
            "source": "catalog",
        },
        {
            "profile": "coding",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_coding",
            "source": "catalog",
        },
        {
            "profile": "vlm",
            "capability": "chat",
            "title_i18n_key": "modelAccessDefault_vlm",
            "source": "catalog",
        },
        {
            "profile": "embedding",
            "capability": "embedding",
            "title_i18n_key": "modelAccessDefault_embedding",
            "source": "provider_models",
        },
        {
            "profile": "extractor",
            "capability": "extractor",
            "title_i18n_key": "modelAccessDefault_extractor",
            "source": "provider_models",
        },
        {
            "profile": "stt",
            "capability": "stt",
            "title_i18n_key": "modelAccessDefault_stt",
            "source": "provider_models",
        },
        {
            "profile": "tts",
            "capability": "tts",
            "title_i18n_key": "modelAccessDefault_tts",
            "source": "provider_models",
        },
    )


def _invalidate_non_llm_provider_caches(kind: str) -> None:
    invalidate_operator_settings_cache()
    if kind == "chat":
        from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

        invalidate_model_catalog_cache()
    elif kind == "embedding":
        from apps.backend.infrastructure.embedding_catalog_providers import (
            invalidate_embedding_provider_specs_cache,
        )

        invalidate_embedding_provider_specs_cache()
    elif kind in {"voice_stt", "voice_tts"}:
        from apps.backend.infrastructure.voice_catalog_providers import (
            invalidate_voice_provider_specs_cache,
        )

        invalidate_voice_provider_specs_cache()
    elif kind == "extractor":
        from apps.backend.infrastructure.extractor_catalog_providers import (
            invalidate_extractor_provider_specs_cache,
        )

        invalidate_extractor_provider_specs_cache()


@app.get("/v1/admin/external-llm/endpoints")
async def admin_get_external_llm_endpoints(request: Request):
    """Legacy path; chat providers are stored in operator_provider_endpoints."""
    await require_admin(request)
    payload = await admin_get_operator_provider_endpoints(request, "chat")
    return {
        "endpoints": [
            {**row, "model_vlm": None, "model_agent": None, "model_coding": None}
            for row in payload.get("endpoints", [])
        ]
    }


def _env_llm_cleanup_keys(index: int) -> list[str]:
    prefix = f"LLM_PROVIDER_{int(index)}"
    return [
        f"{prefix}_BASE_URL",
        f"{prefix}_LABEL",
        f"{prefix}_API_KEY",
        f"{prefix}_API_HEADER_NAME",
        f"{prefix}_MODEL_DEFAULT",
        f"{prefix}_MODEL_VLM",
        f"{prefix}_MODEL_AGENT",
        f"{prefix}_MODEL_CODING",
        f"{prefix}_MAX_PARALLEL",
    ]


def _external_llm_endpoint_public_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("id")) if row.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def _env_llm_provider_preview_rows() -> list[dict[str, Any]]:
    return _operator_env_provider_preview_rows("chat")


@app.get("/v1/admin/external-llm/env-providers")
async def admin_get_external_llm_env_providers(request: Request):
    """Preview numbered LLM_PROVIDER_N_* env providers for explicit DB import."""
    await require_admin(request)
    providers = _env_llm_provider_preview_rows()
    return {
        "providers": providers,
        "count": len(providers),
        "cleanup_note": "Remove imported LLM_PROVIDER_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
    }


@app.post("/v1/admin/external-llm/env-providers/import")
async def admin_import_external_llm_env_providers(
    request: Request,
    body: EnvLlmProvidersImportBody = EnvLlmProvidersImportBody(),
):
    """Legacy path; import chat env providers into generic provider endpoints."""
    await require_admin(request)
    return await admin_import_operator_env_providers(request, "chat", body)


@app.put("/v1/admin/external-llm/endpoints")
async def admin_put_external_llm_endpoints(request: Request, body: ExternalLlmEndpointsPutBody):
    """Legacy path; replace/sync chat endpoints in generic provider storage."""
    await require_admin(request)
    generic = OperatorProviderEndpointsPutBody(
        endpoints=[
            OperatorProviderEndpointItem(
                id=e.id,
                sort_order=e.sort_order,
                enabled=e.enabled,
                label=e.label,
                base_url=e.base_url,
                api_key=e.api_key,
                api_header_name=e.api_header_name,
                model_default=e.model_default,
                max_parallel=e.max_parallel,
            )
            for e in body.endpoints
        ]
    )
    payload = await admin_put_operator_provider_endpoints(request, "chat", generic)
    return {
        "endpoints": [
            {**row, "model_vlm": None, "model_agent": None, "model_coding": None}
            for row in payload.get("endpoints", [])
        ]
    }


@app.get("/v1/admin/model-catalog")
async def admin_get_model_catalog(request: Request):
    """Full model catalog plus admin visibility preferences."""
    await require_admin(request)
    from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog_for_scope

    rows, agentlayer = await asyncio.to_thread(
        fetch_full_model_catalog_for_scope,
        include_hidden=True,
    )
    prefs = await asyncio.to_thread(db.model_catalog_prefs_list_all)
    return {"object": "list", "data": rows, "agentlayer": agentlayer, "prefs": prefs}


@app.get("/v1/admin/llm-providers")
async def admin_get_llm_providers(request: Request):
    """Admin LLM provider catalog shared by LLM settings, chat defaults and benchmarks."""
    await require_admin(request)
    from apps.backend.infrastructure.model_catalog_providers import list_admin_llm_provider_rows

    return {"ok": True, "providers": await asyncio.to_thread(list_admin_llm_provider_rows)}


@app.put("/v1/admin/model-catalog/prefs")
async def admin_put_model_catalog_prefs(request: Request, body: ModelCatalogPrefsPutBody):
    """Upsert model catalog preferences such as chat visibility."""
    await require_admin(request)
    raw = [p.model_dump() for p in body.prefs]
    try:
        await asyncio.to_thread(db.model_catalog_prefs_sync, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

    invalidate_model_catalog_cache()
    return await admin_get_model_catalog(request)


def _model_access_payload_for_scope(scope: str, tenant_id: int | None = None, user_id: uuid.UUID | None = None) -> dict[str, Any]:
    from apps.backend.infrastructure.model_access_policy import effective_policy_preview

    return effective_policy_preview(scope=scope, tenant_id=tenant_id, user_id=user_id)


def _sync_model_access_payload(
    scope: str,
    body: ModelAccessPoliciesPutBody,
    *,
    tenant_id: int | None = None,
    user_id: uuid.UUID | None = None,
) -> None:
    db.model_access_policies_sync(
        scope,
        [x.model_dump() for x in body.model_access],
        tenant_id=tenant_id,
        user_id=user_id,
    )
    db.model_default_policies_sync(
        scope,
        [x.model_dump() for x in body.model_defaults],
        tenant_id=tenant_id,
        user_id=user_id,
    )
    db.provider_capability_policies_sync(
        scope,
        [x.model_dump() for x in body.provider_capabilities],
        tenant_id=tenant_id,
        user_id=user_id,
    )
    from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

    invalidate_model_catalog_cache()


@app.get("/v1/admin/model-access/global")
async def admin_get_global_model_access(request: Request):
    await require_admin(request)
    return _model_access_payload_for_scope("global")


@app.put("/v1/admin/model-access/global")
async def admin_put_global_model_access(request: Request, body: ModelAccessPoliciesPutBody):
    await require_admin(request)
    try:
        await asyncio.to_thread(_sync_model_access_payload, "global", body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("global")


@app.get("/v1/admin/model-access/tenants/{tenant_id}")
async def admin_get_tenant_model_access(request: Request, tenant_id: int):
    await require_admin(request)
    if not db.tenant_exists(tenant_id):
        raise HTTPException(status_code=404, detail="tenant not found")
    return _model_access_payload_for_scope("tenant", tenant_id=tenant_id)


@app.put("/v1/admin/model-access/tenants/{tenant_id}")
async def admin_put_tenant_model_access(request: Request, tenant_id: int, body: ModelAccessPoliciesPutBody):
    await require_admin(request)
    if not db.tenant_exists(tenant_id):
        raise HTTPException(status_code=404, detail="tenant not found")
    try:
        await asyncio.to_thread(_sync_model_access_payload, "tenant", body, tenant_id=tenant_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("tenant", tenant_id=tenant_id)


@app.get("/v1/admin/model-access/users/{user_id}")
async def admin_get_user_model_access(request: Request, user_id: uuid.UUID):
    await require_admin(request)
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    return _model_access_payload_for_scope("user", tenant_id=db.user_tenant_id(user_id), user_id=user_id)


@app.put("/v1/admin/model-access/users/{user_id}")
async def admin_put_user_model_access(request: Request, user_id: uuid.UUID, body: ModelAccessPoliciesPutBody):
    await require_admin(request)
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")
    tenant_id = db.user_tenant_id(user_id)
    try:
        await asyncio.to_thread(_sync_model_access_payload, "user", body, tenant_id=tenant_id, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _model_access_payload_for_scope("user", tenant_id=tenant_id, user_id=user_id)


@app.get("/v1/admin/provider-endpoints")
async def admin_get_operator_provider_endpoint_kinds(request: Request):
    """List backend-owned non-LLM provider endpoint kinds for Admin UI discovery."""
    await require_admin(request)
    return {
        "kinds": list(_operator_provider_endpoint_metadata()),
        "model_default_profiles": list(_model_default_profile_metadata()),
    }


@app.get("/v1/admin/provider-endpoints/{kind}")
async def admin_get_operator_provider_endpoints(request: Request, kind: str):
    """List non-LLM provider endpoints (keys redacted), using LLM-style endpoint rows."""
    await require_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    out: list[dict[str, Any]] = []
    for r in db.operator_provider_endpoints_list_all(kind_v):
        provider_id = _operator_endpoint_provider_id(kind_v, int(r["id"]))
        model_payload = await _operator_provider_models_payload(kind_v, provider_id)
        k = str(r.get("api_key") or "")
        out.append(
            {
                "id": r["id"],
                "kind": r["kind"],
                "provider_id": provider_id,
                "source": "db",
                "sort_order": r["sort_order"],
                "enabled": r["enabled"],
                "label": r.get("label") or "",
                "base_url": r.get("base_url") or "",
                "api_key_configured": bool(k.strip()),
                "api_key_last4": (k[-4:] if len(k) >= 4 else None),
                "api_header_name": (str(r.get("api_header_name") or "").strip() or "Authorization"),
                "model_default": r.get("model_default"),
                "max_parallel": int(r.get("max_parallel") or 1),
                "options_json": r.get("options_json") if isinstance(r.get("options_json"), dict) else {},
                "models": [str(row.get("id") or "").strip() for row in model_payload.get("data", []) if str(row.get("id") or "").strip()],
                "models_detail": model_payload.get("detail"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
            }
        )
    return {"endpoints": out}


def _operator_env_prefix(kind: str, index: int) -> str:
    if kind == "chat":
        return f"LLM_PROVIDER_{int(index)}"
    if kind == "embedding":
        return f"EMBEDDING_PROVIDER_{int(index)}"
    if kind == "extractor":
        return f"EXTRACTOR_PROVIDER_{int(index)}"
    if kind == "voice_stt":
        return f"VOICE_STT_PROVIDER_{int(index)}"
    if kind == "voice_tts":
        return f"VOICE_TTS_PROVIDER_{int(index)}"
    raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")


def _operator_env_cleanup_keys(kind: str, index: int) -> list[str]:
    prefix = _operator_env_prefix(kind, index)
    if kind == "chat":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL_DEFAULT",
            "MODEL_VLM",
            "MODEL_AGENT",
            "MODEL_CODING",
            "MAX_PARALLEL",
        ]
    elif kind == "embedding":
        suffixes = ["BASE_URL", "LABEL", "API_KEY", "API_HEADER_NAME", "MODEL_DEFAULT"]
    elif kind == "extractor":
        suffixes = ["BASE_URL", "NAME", "LABEL", "API_KEY", "API_HEADER_NAME", "MODEL", "TIMEOUT_SEC"]
    elif kind == "voice_stt":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL",
            "MODEL_STT",
            "API_STYLE",
            "STT_API_STYLE",
            "TRANSCRIBE_PATH",
            "STT_PATH",
        ]
    elif kind == "voice_tts":
        suffixes = [
            "BASE_URL",
            "LABEL",
            "API_KEY",
            "API_HEADER_NAME",
            "MODEL",
            "MODEL_TTS",
            "MODEL_TTS_VOICE",
            "VOICE",
        ]
    else:
        suffixes = []
    return [f"{prefix}_{s}" for s in suffixes]


def _operator_env_rows_for_kind(kind: str):
    if kind == "chat":
        return parse_llm_env_providers()
    if kind == "embedding":
        return parse_embedding_env_providers()
    if kind == "extractor":
        return parse_extractor_env_providers()
    if kind == "voice_stt":
        return parse_voice_stt_env_providers()
    if kind == "voice_tts":
        return parse_voice_tts_env_providers()
    raise HTTPException(status_code=404, detail="Unknown provider endpoint kind.")


def _operator_env_options(kind: str, row: Any) -> dict[str, Any]:
    if kind == "extractor":
        return {"timeout_sec": float(getattr(row, "timeout_sec", 120.0))}
    if kind == "voice_stt":
        return {
            "stt_api_style": getattr(row, "stt_api_style", "openai"),
            "stt_transcribe_path": getattr(row, "stt_transcribe_path", None),
        }
    if kind == "voice_tts":
        return {"model_tts_voice": getattr(row, "model_tts_voice", None)}
    return {}


def _operator_env_model(kind: str, row: Any) -> str | None:
    if kind in {"voice_stt", "voice_tts"}:
        return str(getattr(row, "model", "") or "").strip() or None
    return str(getattr(row, "model_default", "") or "").strip() or None


def _operator_provider_endpoint_public_id(row: dict[str, Any]) -> int | None:
    try:
        return int(row.get("id")) if row.get("id") is not None else None
    except (TypeError, ValueError):
        return None


def _operator_provider_base_url(raw: Any) -> str:
    """Preserve the configured OpenAI-compatible base path for non-chat providers."""
    return str(raw or "").strip().strip("'\"").rstrip("/")


def _operator_provider_dedupe_key(raw: Any) -> str:
    """Compare equivalent OpenAI-compatible bases without changing what we store/display."""
    base = _operator_provider_base_url(raw)
    return (normalize_external_llm_base_url(base) or base).lower()


def _operator_env_provider_preview_rows(kind: str) -> list[dict[str, Any]]:
    kind_v = _operator_provider_kind_or_404(kind)
    db_rows = db.operator_provider_endpoints_list_all(kind_v)
    db_by_base: dict[str, dict[str, Any]] = {}
    for row in db_rows:
        key = _operator_provider_dedupe_key(row.get("base_url"))
        if key:
            db_by_base.setdefault(key, row)

    out: list[dict[str, Any]] = []
    for row in _operator_env_rows_for_kind(kind_v):
        base = _operator_provider_base_url(row.base_url)
        match = db_by_base.get(_operator_provider_dedupe_key(base))
        key = str(getattr(row, "api_key", "") or "")
        out.append(
            {
                "kind": kind_v,
                "index": int(getattr(row, "index")),
                "provider_id": getattr(row, "provider_id"),
                "label": getattr(row, "label"),
                "base_url": base,
                "api_key_configured": bool(key.strip()),
                "api_key_last4": key[-4:] if len(key) >= 4 else None,
                "api_header_name": getattr(row, "api_header_name", None) or "Authorization",
                "model_default": _operator_env_model(kind_v, row),
                "max_parallel": int(getattr(row, "max_parallel", 1) or 1),
                "options_json": _operator_env_options(kind_v, row),
                "cleanup_keys": _operator_env_cleanup_keys(kind_v, int(getattr(row, "index"))),
                "already_in_db": match is not None,
                "matched_db_endpoint_id": _operator_provider_endpoint_public_id(match or {}),
            }
        )
    return out


@app.get("/v1/admin/provider-endpoints/{kind}/env-providers")
async def admin_get_operator_env_providers(request: Request, kind: str):
    """Preview non-LLM numbered env providers for explicit DB import."""
    await require_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    providers = _operator_env_provider_preview_rows(kind_v)
    return {
        "providers": providers,
        "count": len(providers),
        "cleanup_note": f"Remove imported {_operator_env_prefix(kind_v, 1).rsplit('_', 1)[0]}_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
    }


def _provider_models_url(base_url: str) -> str:
    base = _operator_provider_base_url(base_url)
    low = base.lower()
    if low.endswith("/models"):
        return base
    if low.endswith("/v1"):
        return f"{base}/models"
    return f"{base}/v1/models"


def _provider_auth_headers(api_key: str, api_header_name: str) -> dict[str, str]:
    key = (api_key or "").strip()
    if not key:
        return {}
    header = (api_header_name or "Authorization").strip() or "Authorization"
    if header.lower() == "authorization":
        return {"Authorization": key if key.lower().startswith("bearer ") else f"Bearer {key}"}
    return {header: key}


def _provider_configured_model_rows(spec: Any) -> list[dict[str, str]]:
    ids: list[str] = []
    for attr in ("model_default", "model", "model_stt", "model_tts"):
        value = str(getattr(spec, attr, "") or "").strip()
        if value and value not in ids:
            ids.append(value)
    return [{"id": model_id} for model_id in ids]


@app.get("/v1/admin/provider-endpoints/{kind}/models")
async def admin_operator_provider_models(request: Request, kind: str, provider_id: str | None = None):
    """List model ids for one non-LLM provider. Used by Admin dropdowns."""
    await require_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    return await _operator_provider_models_payload(kind_v, provider_id)


async def _operator_provider_models_payload(kind_v: str, provider_id: str | None = None) -> dict[str, Any]:
    if kind_v == "chat":
        from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog_for_scope

        rows, _agentlayer = await asyncio.to_thread(fetch_full_model_catalog_for_scope, include_hidden=True)
        pid = (provider_id or "").strip().lower()
        if pid.startswith("chat_provider_db_"):
            pid = "provider_db_" + pid[len("chat_provider_db_") :]
        data = [
            {"id": str(row.get("id") or "").strip()}
            for row in rows
            if (not pid or str(row.get("owned_by") or "").strip().lower() == pid)
            and str(row.get("id") or "").strip()
        ]
        return {"data": data}
    if kind_v == "embedding":
        from apps.backend.infrastructure.embedding_client import fetch_embedding_models_list

        models, detail = await asyncio.to_thread(fetch_embedding_models_list, provider_id=provider_id, timeout=12.0)
        return {"data": [{"id": m} for m in models], "detail": detail}

    spec: Any = None
    if kind_v == "extractor":
        from apps.backend.infrastructure.extractor_catalog_providers import get_extractor_provider_spec

        spec = get_extractor_provider_spec(provider_id)
    elif kind_v == "voice_stt":
        from apps.backend.infrastructure.voice_catalog_providers import get_voice_stt_provider_spec

        spec = get_voice_stt_provider_spec(provider_id or "")
    elif kind_v == "voice_tts":
        from apps.backend.infrastructure.voice_catalog_providers import get_voice_tts_provider_spec

        spec = get_voice_tts_provider_spec(provider_id or "")
    if spec is None:
        raise HTTPException(status_code=404, detail="Provider not found.")
    fallback_rows = _provider_configured_model_rows(spec)
    url = _provider_models_url(str(spec.base_url))
    try:
        status, text, data = await asyncio.to_thread(
            http_get_json,
            url,
            headers=_provider_auth_headers(str(spec.api_key or ""), str(spec.api_header_name or "Authorization")),
            timeout=12.0,
        )
    except Exception as e:
        return {"data": fallback_rows, "detail": f"Provider model list unavailable: {e}"}
    if status != 200 or not isinstance(data, dict):
        return {
            "data": fallback_rows,
            "detail": (text or "").strip() or f"Provider model list unavailable: HTTP {status}",
        }
    rows = []
    for item in data.get("data") or []:
        if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
            rows.append({"id": item["id"].strip()})
    return {"data": rows}


@app.post("/v1/admin/provider-endpoints/{kind}/env-providers/import")
async def admin_import_operator_env_providers(
    request: Request,
    kind: str,
    body: EnvLlmProvidersImportBody = EnvLlmProvidersImportBody(),
):
    """Import selected non-LLM env providers into DB endpoints without modifying .env."""
    await require_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    selected = {int(i) for i in body.provider_indexes or [] if int(i) >= 1}
    env_rows = [
        row
        for row in _operator_env_rows_for_kind(kind_v)
        if not selected or int(getattr(row, "index")) in selected
    ]
    existing = db.operator_provider_endpoints_list_all(kind_v)
    combined: list[dict[str, Any]] = []
    base_to_pos: dict[str, int] = {}
    for row in existing:
        clone = dict(row)
        combined.append(clone)
        key = _operator_provider_dedupe_key(row.get("base_url"))
        if key:
            base_to_pos.setdefault(key, len(combined) - 1)

    imported: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    for env_row in env_rows:
        base = _operator_provider_base_url(env_row.base_url)
        payload = {
            "sort_order": len(combined),
            "enabled": True,
            "label": getattr(env_row, "label"),
            "base_url": base,
            "api_key": getattr(env_row, "api_key", ""),
            "api_header_name": getattr(env_row, "api_header_name", None) or "Authorization",
            "model_default": _operator_env_model(kind_v, env_row),
            "max_parallel": int(getattr(env_row, "max_parallel", 1) or 1),
            "options_json": _operator_env_options(kind_v, env_row),
        }
        key = _operator_provider_dedupe_key(base)
        pos = base_to_pos.get(key)
        if pos is None:
            combined.append(payload)
            base_to_pos[key] = len(combined) - 1
            imported.append(
                {"index": getattr(env_row, "index"), "provider_id": getattr(env_row, "provider_id"), "base_url": base}
            )
        else:
            prev = combined[pos]
            combined[pos] = {**prev, **payload, "id": prev.get("id"), "sort_order": prev.get("sort_order", pos)}
            updated.append(
                {
                    "index": getattr(env_row, "index"),
                    "provider_id": getattr(env_row, "provider_id"),
                    "base_url": base,
                    "db_endpoint_id": _operator_provider_endpoint_public_id(prev),
                }
            )

    try:
        db.operator_provider_endpoints_sync(kind_v, combined)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_non_llm_provider_caches(kind_v)
    return {
        "ok": True,
        "imported": imported,
        "updated": updated,
        "cleanup_keys": [
            key
            for row in env_rows
            for key in _operator_env_cleanup_keys(kind_v, int(getattr(row, "index")))
        ],
        "cleanup_note": f"Remove imported {_operator_env_prefix(kind_v, 1).rsplit('_', 1)[0]}_N_* keys from .env/deployment env and restart to avoid duplicate providers.",
        "endpoints": (await admin_get_operator_provider_endpoints(request, kind_v))["endpoints"],
        "env_providers": _operator_env_provider_preview_rows(kind_v),
    }


@app.put("/v1/admin/provider-endpoints/{kind}")
async def admin_put_operator_provider_endpoints(
    request: Request,
    kind: str,
    body: OperatorProviderEndpointsPutBody,
):
    """Replace/sync non-LLM provider endpoints for one kind."""
    await require_admin(request)
    kind_v = _operator_provider_kind_or_404(kind)
    raw = [e.model_dump() for e in body.endpoints]
    try:
        db.operator_provider_endpoints_sync(
            kind_v,
            raw,
            delete_missing=False,
            delete_ids=body.delete_endpoint_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    _invalidate_non_llm_provider_caches(kind_v)
    return await admin_get_operator_provider_endpoints(request, kind_v)


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
    media_storage_quota_mb: int | None = Field(default=None, ge=1, le=50_000)
    media_enabled: bool | None = None
    media_upload_enabled: bool | None = None
    media_sharing_enabled: bool | None = None
    llm_queue_priority: int | None = Field(default=None, ge=0, le=1000)


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
            from apps.backend.infrastructure.llm_queue_policy import invalidate_user_priority_cache

            invalidate_user_priority_cache(user_id)
        except Exception:
            pass

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
        """Legacy deep links: Coding UI removed; Chat is the only project surface."""
        q = request.url.query
        target = "/app/chat" + (f"?{q}" if q else "")
        return RedirectResponse(url=target, status_code=302)

    @app.get("/app")
    async def agent_ui_spa_root():
        """``/app`` without trailing slash: same shell as ``/app/`` (hard refresh must not 405)."""
        return FileResponse(_agent_index)

    @app.get("/app/chat")
    @app.get("/app/coding-agent")
    @app.get("/app/dashboard")
    @app.get("/app/dashboard/shared")
    @app.get("/app/docs")
    @app.get("/app/login")
    @app.get("/app/setup")
    @app.get("/app/schedules")
    @app.get("/app/tasks")
    @app.get("/app/settings")
    @app.get("/app/settings/profile")
    @app.get("/app/settings/voice")
    @app.get("/app/settings/connections")
    @app.get("/app/settings/notifications")
    @app.get("/app/settings/tools")
    @app.get("/app/settings/agent")
    @app.get("/app/settings/delegate")
    @app.get("/app/settings/friends")
    @app.get("/app/settings/shares")
    @app.get("/app/studio")
    @app.get("/app/admin")
    @app.get("/app/admin/interfaces")
    @app.get("/app/admin/interfaces/bridges")
    @app.get("/app/admin/interfaces/llm")
    @app.get("/app/admin/interfaces/providers")
    @app.get("/app/admin/interfaces/model-policies")
    @app.get("/app/admin/interfaces/routing")
    @app.get("/app/admin/interfaces/memory")
    @app.get("/app/admin/interfaces/voice")
    @app.get("/app/admin/interfaces/automation")
    @app.get("/app/admin/interfaces/platform")
    @app.get("/app/admin/interfaces/{rest:path}")
    @app.get("/app/admin/tools")
    @app.get("/app/admin/agents")
    @app.get("/app/admin/benchmarks")
    @app.get("/app/admin/agent-config")
    @app.get("/app/admin/run-traces")
    @app.get("/app/admin/users")
    @app.get("/app/admin/scheduled-jobs")
    @app.get("/app/admin/schedules")
    @app.get("/app/admin/workflows")
    @app.get("/app/admin/agent-config/{rest:path}")
    async def agent_ui_spa_shell():
        """Serve SPA index for client-side routes (must register before mount /app)."""
        return FileResponse(_agent_index)

    app.mount(
        "/app",
        StaticFiles(directory=str(_agent_ui_dir), html=True),
        name="agent_ui",
    )

_cors_origins = [
    o.strip() for o in os.environ.get("AGENT_CORS_ORIGINS", "").split(",") if o.strip()
]
# Default: no CORS (deny all). Operator must set AGENT_CORS_ORIGINS for production.
_cors_credentials = "*" not in _cors_origins if _cors_origins else False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or [],
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

    if is_media_stream_route(path, request.method):
        return await call_next(request)

    if is_dashboard_public_share_route(path, request.method):
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
    env_provider_rows: list[dict[str, Any]],
    llama_cpp_rows: list[dict[str, Any]],
    *more: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-export: dedupe by ``(owned_by, id)``; same id on different providers stays separate."""
    from apps.backend.infrastructure.model_catalog_providers import merge_model_catalog_rows as _merge

    return _merge(env_provider_rows, llama_cpp_rows, *more)


@app.get("/v1/models")
async def models_proxy(request: Request):
    """
    OpenAI-style model list: all catalog providers (``provider_1``, ``provider_2``, external endpoints, …).

    One provider failing does not remove rows from others. ``agentlayer`` keys match row ``owned_by``.
    """
    user = await get_current_user(request)
    from apps.backend.infrastructure.model_catalog_providers import fetch_full_model_catalog

    merged, agentlayer = await asyncio.to_thread(
        fetch_full_model_catalog,
        tenant_id=db.user_tenant_id(user.id),
        user_id=user.id,
    )
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
    user_tz = (request.headers.get("X-User-Timezone") or "").strip() or None

    try:
        result = await chat_completion(
            work,
            router_categories_header=router_hdr,
            tool_domain_header=tool_dom_hdr,
            model_profile_header=model_prof,
            model_override_header=model_ovr,
            user_timezone_header=user_tz,
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