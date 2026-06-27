"""Side-effect dependencies used by legacy agent runtime modules during DDD migration."""

from __future__ import annotations

from apps.backend.api import memory as memory_api
from apps.backend.api.rag import embed_one
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.file_upload import upload_dashboard_image
from apps.backend.dashboard.layout_tree import find_block_in_layout, iter_layout_blocks
from apps.backend.dashboard.setup import onboarding_for_dashboard
from apps.backend.infrastructure import (
    agent_artifacts_store,
    agent_config_effective,
    agent_runs_store,
    agent_tasks_store,
)
from apps.backend.infrastructure.agent_config_task_intent import (
    categories_for_matches,
    hints_for_matches,
    match_task_intents,
    task_intent_strict_tools,
    tools_for_matches,
)
from apps.backend.infrastructure.chat_context import (
    ContextPrepMeta,
    apply_budget_to_meta,
    prepare_chat_history_for_llm,
    update_meta_from_provider_usage,
)
from apps.backend.infrastructure.chat_context_loop import apply_agent_loop_context_budget
from apps.backend.infrastructure.chat_secret_ingress import ingress_openai_messages_inplace
from apps.backend.infrastructure.context_budget import (
    completion_quotas_from_budget,
    resolve_context_budget,
    usage_prompt_tokens,
)
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.knowledge_orchestration_prompt import (
    build_knowledge_orchestration_snippet,
)
from apps.backend.infrastructure.llm_chat_attempt import unpack_llm_attempt
from apps.backend.infrastructure.llm_concurrency import (
    bind_llm_wait_notifier,
    llm_slot_async,
    reset_llm_wait_notifier,
)
from apps.backend.infrastructure.mcp_runtime import gather_mcp_chat_tool_specs_async
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.openai_stream_aggregate import stream_chat_completions_aggregate
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
)
from apps.backend.infrastructure.skills_prompt import load_combined_skills_prompt
from apps.backend.infrastructure.stream_repetition_guard import apply_repetition_guard_to_completion
from apps.backend.infrastructure.tool_operator_policy_db import policies_map
from apps.backend.infrastructure.user_secrets_bootstrap import (
    build_user_secrets_bootstrap_snippet,
    build_workspace_bound_snippet,
)
from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
    build_retrieval_bootstrap_snippet,
    maybe_schedule_index_on_attach,
)
from apps.backend.infrastructure.workspace_service import (
    WorkspaceCreateError,
    create_project_workspace_for_user,
    ensure_workspace,
    slug_from_git_url,
)
