"""Side-effect dependencies used by legacy agent runtime modules during DDD migration."""

from __future__ import annotations

from apps.backend.infrastructure.memory import memory_service as memory_api
from apps.backend.infrastructure.rag.rag_core import embed_one
from apps.backend.infrastructure.dashboards.dashboard_layout_tree import find_block_in_layout, iter_layout_blocks
from apps.backend.infrastructure.dashboards.dashboard_setup import onboarding_for_dashboard
from apps.backend.infrastructure.agent_runtime import (
    agent_artifacts_store,
    agent_config_effective,
    agent_runs_store,
    agent_tasks_store,
)
from apps.backend.infrastructure.dashboards import dashboard_db
from apps.backend.infrastructure.dashboards.dashboard_file_upload import upload_dashboard_image
from apps.backend.infrastructure.agent_runtime.agent_config_task_intent import (
    categories_for_matches,
    hints_for_matches,
    match_task_intents,
    task_intent_strict_tools,
    tools_for_matches,
)
from apps.backend.infrastructure.agent_runtime.chat_context import (
    ContextPrepMeta,
    apply_budget_to_meta,
    prepare_chat_history_for_llm,
    update_meta_from_provider_usage,
)
from apps.backend.infrastructure.agent_runtime.chat_context_loop import apply_agent_loop_context_budget
from apps.backend.infrastructure.platform.chat_secret_ingress import ingress_openai_messages_inplace
from apps.backend.infrastructure.agent_runtime.chat_audio_attachment_service import (
    format_ingested_audio_system_block,
    ingest_chat_audio_attachments,
)
from apps.backend.infrastructure.agent_runtime.context_budget import (
    completion_quotas_from_budget,
    resolve_context_budget,
    usage_prompt_tokens,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.memory.knowledge_orchestration_prompt import (
    build_knowledge_orchestration_snippet,
)
from apps.backend.infrastructure.agent_runtime.llm_chat_attempt import unpack_llm_attempt
from apps.backend.infrastructure.agent_runtime.llm_concurrency import (
    bind_llm_wait_notifier,
    llm_slot_async,
    reset_llm_wait_notifier,
)
from apps.backend.infrastructure.agent_runtime.media_chat_prompt_service import build_media_library_context_snippet
from apps.backend.infrastructure.plugins.mcp_runtime import gather_mcp_chat_tool_specs_async
from apps.backend.infrastructure.providers.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.agent_runtime.openai_stream_aggregate import stream_chat_completions_aggregate
from apps.backend.infrastructure.settings.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
)
from apps.backend.infrastructure.plugins.skills_prompt import load_combined_skills_prompt
from apps.backend.infrastructure.agent_runtime.stream_repetition_guard import apply_repetition_guard_to_completion
from apps.backend.infrastructure.tools.tool_operator_policy_db import policies_map
from apps.backend.infrastructure.platform.user_secrets_bootstrap import (
    build_user_secrets_bootstrap_snippet,
    build_workspace_bound_snippet,
)
from apps.backend.infrastructure.workspace.workspace_retrieval_bootstrap import (
    build_retrieval_bootstrap_snippet,
    maybe_schedule_index_on_attach,
)
from apps.backend.infrastructure.workspace.workspace_service import (
    WorkspaceCreateError,
    create_project_workspace_for_user,
    ensure_workspace,
    slug_from_git_url,
)
