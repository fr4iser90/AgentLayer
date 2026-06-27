"""FastAPI composition root for AgentLayer."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.backend.application.platform.use_cases.server_lifecycle import (
    authenticate_request,
    configure_server_logging,
    server_lifespan,
)
from apps.backend.api.platform.controllers.optional_http_access import (
    is_dashboard_public_share_route,
    is_identity_deferred_route,
    is_media_stream_route,
    middleware_path_is_public,
)

from apps.backend.api.platform.controllers.user_data_api import router as user_data_router
from apps.backend.api.delegation.controllers.delegate_api import router as delegate_router
from apps.backend.api.rag.controllers.memory_api import router as memory_router
from apps.backend.api.platform.controllers.user_secrets_api import router as user_secrets_router
from apps.backend.api.agents.controllers.agent_config_admin_api import router as agent_config_admin_router
from apps.backend.api.agents.controllers.agents_admin_api import router as agents_admin_router
from apps.backend.api.agents.controllers.agents_api import router as agents_router
from apps.backend.api.agents.controllers.agents_import_admin_api import router as agents_import_admin_router
from apps.backend.api.agents.controllers.session_runtime_api import router as session_runtime_router
from apps.backend.api.benchmarks.controllers.benchmark_harness_admin_api import router as benchmark_harness_admin_router
from apps.backend.api.benchmarks.controllers.benchmarks_admin_api import router as benchmarks_admin_router
from apps.backend.api.chat.controllers.chat_completions_api import router as chat_completions_router
from apps.backend.api.chat.controllers.chat_websocket import router as chat_ws_router
from apps.backend.api.chat.controllers.message_feedback_api import admin_router as message_feedback_admin_router
from apps.backend.api.chat.controllers.message_feedback_api import router as message_feedback_router
from apps.backend.api.chat.controllers.run_traces_admin_api import router as run_traces_admin_router
from apps.backend.api.codebase.controllers.codebase_api import router as codebase_router
from apps.backend.api.conversations.controllers.conversations_api import router as conversations_router
from apps.backend.api.dashboards.controllers.dashboard_api import router as dashboard_router
from apps.backend.api.media.controllers.media_api import router as media_router
from apps.backend.api.notifications.controllers.notifications_api import router as notifications_router
from apps.backend.api.platform.controllers.admin_users_api import router as admin_users_router
from apps.backend.api.platform.controllers.auth_api import router as auth_router
from apps.backend.api.platform.controllers.health_api import merge_model_catalog_rows
from apps.backend.api.platform.controllers.health_api import router as health_router
from apps.backend.api.platform.controllers.web_api import register_web_routes
from apps.backend.api.providers.controllers.operator_admin_api import router as operator_admin_router
from apps.backend.api.projects.controllers.github_api import router as github_router
from apps.backend.api.projects.controllers.project_runs_api import router as project_runs_router
from apps.backend.api.rag.controllers.rag_api import router as rag_router
from apps.backend.api.scheduling.controllers.scheduler_job_presets_api import router as scheduler_job_presets_router
from apps.backend.api.scheduling.controllers.scheduler_job_presets_user_api import router as scheduler_job_presets_user_router
from apps.backend.api.scheduling.controllers.scheduler_job_runs_api import admin_router as scheduler_job_runs_admin_router
from apps.backend.api.scheduling.controllers.scheduler_job_runs_api import user_router as scheduler_job_runs_user_router
from apps.backend.api.scheduling.controllers.scheduler_jobs_admin_api import router as scheduler_jobs_admin_router
from apps.backend.api.scheduling.controllers.scheduler_jobs_user_api import router as scheduler_jobs_user_router
from apps.backend.api.sharing.controllers.friends_api import router as friends_router
from apps.backend.api.sharing.controllers.shares_api import router as shares_router
from apps.backend.api.studio.controllers.studio_api import router as studio_router
from apps.backend.api.tasks.controllers.task_artifacts_api import router as task_artifacts_router
from apps.backend.api.tasks.controllers.tasks_api import router as tasks_router
from apps.backend.api.tools.controllers.openapi_tools_api import router as openapi_tools_router
from apps.backend.api.tools.controllers.tools_admin_api import router as tools_admin_router
from apps.backend.api.tools.controllers.tools_api import router as tools_router
from apps.backend.api.tools.controllers.tools_import_admin_api import router as tools_import_admin_router
from apps.backend.api.voice.controllers.voice_api import router as voice_router
from apps.backend.api.voice.controllers.voice_realtime_websocket import router as voice_realtime_ws_router
from apps.backend.api.workspaces.controllers.workspaces_admin_api import router as workspaces_admin_router
from apps.backend.api.workspaces.controllers.workspaces_api import router as workspaces_router

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
configure_server_logging()
logger = logging.getLogger(__name__)


app = FastAPI(title="agent-layer", version="0.7.7", lifespan=server_lifespan)

for router in (
    user_secrets_router,
    conversations_router,
    message_feedback_router,
    message_feedback_admin_router,
    dashboard_router,
    media_router,
    voice_router,
    voice_realtime_ws_router,
    user_data_router,
    notifications_router,
    delegate_router,
    memory_router,
    tools_router,
    rag_router,
    codebase_router,
    chat_ws_router,
    chat_completions_router,
    studio_router,
    scheduler_jobs_admin_router,
    scheduler_job_presets_router,
    scheduler_jobs_user_router,
    scheduler_job_runs_user_router,
    scheduler_job_runs_admin_router,
    scheduler_job_presets_user_router,
    project_runs_router,
    tasks_router,
    task_artifacts_router,
    run_traces_admin_router,
    benchmarks_admin_router,
    agent_config_admin_router,
    benchmark_harness_admin_router,
    agents_router,
    agents_admin_router,
    agents_import_admin_router,
    tools_admin_router,
    tools_import_admin_router,
    session_runtime_router,
    friends_router,
    shares_router,
    workspaces_router,
    workspaces_admin_router,
    github_router,
    auth_router,
    operator_admin_router,
    admin_users_router,
    health_router,
    openapi_tools_router,
):
    app.include_router(router)

register_web_routes(app)

_cors_origins = [
    o.strip() for o in os.environ.get("AGENT_CORS_ORIGINS", "").split(",") if o.strip()
]
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
    if (request.method or "").upper() == "OPTIONS":
        return await call_next(request)
    if middleware_path_is_public(path, request.method):
        return await call_next(request)
    if is_identity_deferred_route(path, request.method):
        return await call_next(request)
    if is_media_stream_route(path, request.method):
        return await call_next(request)
    if is_dashboard_public_share_route(path, request.method):
        return await call_next(request)
    try:
        await authenticate_request(request)
    except HTTPException:
        return JSONResponse(status_code=401, content={"error": "unauthorized"})
    return await call_next(request)
