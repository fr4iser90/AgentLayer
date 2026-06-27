from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request

from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.infrastructure.agent_runtime import agent_registry_service as _agent_registry_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import agent_run_persistence_service as _agent_run_persistence_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import agent_task_access_service as _agent_task_access_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import agent_task_prompt_service as _agent_task_prompt_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import assistant_display_sanitize_service as _assistant_display_sanitize_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import chat_audio_attachment_service as _chat_audio_attachment_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import current_time_context_service as _current_time_context_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import media_chat_prompt_service as _media_chat_prompt_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import smart_route_service as _smart_route_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import speech_prep_service as _speech_prep_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime import user_persona_service as _user_persona_service  # noqa: F401
from apps.backend.infrastructure.agent_runtime.agent_tasks_runner import start_agent_tasks_worker, stop_agent_tasks_worker
from apps.backend.infrastructure.collections import collection_share_service as _collection_share_service  # noqa: F401
from apps.backend.infrastructure.collections import collections_db_service as _collections_db_service  # noqa: F401
from apps.backend.infrastructure.collections import collections_view_service as _collections_view_service  # noqa: F401
from apps.backend.infrastructure.dashboards import dashboard_agent_guard_service as _dashboard_agent_guard_service  # noqa: F401
from apps.backend.infrastructure.dashboards import dashboard_grant_service as _dashboard_grant_service  # noqa: F401
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.delegation import delegate_decision_service as _delegate_decision_service  # noqa: F401
from apps.backend.infrastructure.delegation import delegate_enforcement_service as _delegate_enforcement_service  # noqa: F401
from apps.backend.infrastructure.identity import http_identity_service as _http_identity_service  # noqa: F401
from apps.backend.infrastructure.identity.admin_setup import is_first_start
from apps.backend.infrastructure.identity.auth import get_current_user
from apps.backend.infrastructure.identity.instance_setup_service import (
    emit_initial_setup_notice_at_end,
    setup_admin_claim_if_needed,
)
from apps.backend.infrastructure.platform.bridge_lifecycle_service import (
    start_discord_bridge,
    start_telegram_bridge,
    stop_discord_bridge,
    stop_telegram_bridge,
)
from apps.backend.infrastructure.platform.log_redaction import (
    apply_http_client_log_levels,
    install_log_redaction_filters,
)
from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
from apps.backend.infrastructure.projects.project_runs_runner import start_project_runs_worker, stop_project_runs_worker
from apps.backend.infrastructure.rag import rag_ingest_service as _rag_ingest_service  # noqa: F401
from apps.backend.infrastructure.rag.rag_docs_file_ingest_service import run_startup_rag_docs_ingest
from apps.backend.infrastructure.scheduling.cron import start_cron_scheduler, stop_cron_scheduler
from apps.backend.infrastructure.scheduling.scheduler import start_scheduler_worker, stop_scheduler_worker
from apps.backend.infrastructure.scheduling.scheduler_jobs_runner import (
    start_scheduler_jobs_worker,
    stop_scheduler_jobs_worker,
)
from apps.backend.infrastructure.settings import operator_voice_settings_service as _operator_voice_settings_service  # noqa: F401
from apps.backend.infrastructure.tools import tool_forward_policy_service as _tool_forward_policy_service  # noqa: F401
from apps.backend.infrastructure.tools import tool_policy_service as _tool_policy_service  # noqa: F401
from apps.backend.infrastructure.tools import tool_routing_service as _tool_routing_service  # noqa: F401
from apps.backend.infrastructure.tools import tool_runtime_service as _tool_runtime_service  # noqa: F401
from apps.backend.infrastructure.voice import voice_policy_service as _voice_policy_service  # noqa: F401
from apps.backend.infrastructure.voice import voice_realtime_turn_service as _voice_realtime_turn_service  # noqa: F401
from apps.backend.infrastructure.workspace import workspace_common_service as _workspace_common_service  # noqa: F401
from apps.backend.infrastructure.workspace import workspace_rag_ingest_service as _workspace_rag_ingest_service  # noqa: F401
from apps.backend.infrastructure.workspace import workspace_resolver_service as _workspace_resolver_service  # noqa: F401

logger = logging.getLogger(__name__)


def configure_server_logging() -> None:
    install_log_redaction_filters()


async def authenticate_request(request: Request) -> None:
    await get_current_user(request)


@asynccontextmanager
async def server_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    apply_http_client_log_levels()
    db.init_pool()
    try:
        from apps.backend.infrastructure.benchmarks.benchmark_runs_store import (
            reconcile_orphaned_runs_on_startup,
        )

        n = reconcile_orphaned_runs_on_startup()
        if n:
            logger.warning("Marked %s orphaned benchmark run(s) as failed after startup", n)
    except Exception:
        logger.exception("Benchmark orphan reconciliation failed")
    try:
        from apps.backend.infrastructure.agent_runtime.agent_runs_store import (
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
            from apps.backend.infrastructure.rag.rag_embedding_sync import ensure_rag_embedding_aligned

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
    logger.info("RAG embedding sync + docs ingest scheduled in background (API/UI ready immediately)")

    start_cron_scheduler()
    try:
        from apps.backend.infrastructure.workspace.workspace_reindex_scheduler import (
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
        start_discord_bridge()
    except Exception:
        logger.exception("Discord bridge failed to start (optional)")
    try:
        start_telegram_bridge()
    except Exception:
        logger.exception("Telegram bridge failed to start (optional)")
    if is_first_start():
        await asyncio.sleep(0.75)
    emit_initial_setup_notice_at_end()
    yield
    try:
        from apps.backend.infrastructure.benchmarks.benchmark_runner import cancel_all_active_benchmark_runs

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
        stop_discord_bridge()
    except Exception:
        pass
    try:
        stop_telegram_bridge()
    except Exception:
        pass
    stop_cron_scheduler()
    try:
        from apps.backend.infrastructure.workspace.workspace_reindex_scheduler import (
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
