"""SQL persistence for operator settings PATCH updates."""
from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import (
    _bound_float,
    _bound_int,
    _coerce_rag_embedding_dim,
    _discord_trigger_prefix_sql,
    _normalize_http_client_log_level_str,
    _rag_embedding_model_from_row,
    _router_model_from_row,
    _sync_single_provider_endpoint,
    _telegram_trigger_prefix_sql,
    normalize_llm_primary_backend,
    normalize_scheduler_llm_backend,
    normalize_scheduler_tools_mode,
)
from apps.backend.infrastructure.settings.operator_settings_patch_writer import _maybe_align_pgvector_embedding_dim

def persist_operator_settings_patch(r: dict[str, Any], patch: dict[str, Any], media_patch: dict[str, Any]) -> None:
    _maybe_align_pgvector_embedding_dim(r, patch)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO operator_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
            cur.execute(
                """
                UPDATE operator_settings SET
                  discord_application_id = %s,
                  integration_notes = %s,
                  optional_connection_key = %s,
                  agent_mode = %s,
                  discord_bot_enabled = %s,
                  discord_bot_token = %s,
                  discord_bot_agent_bearer = %s,
                  discord_trigger_prefix = %s,
                  discord_chat_model = %s,
                  telegram_application_id = %s,
                  telegram_bot_enabled = %s,
                  telegram_bot_token = %s,
                  telegram_bot_agent_bearer = %s,
                  telegram_trigger_prefix = %s,
                  telegram_chat_model = %s,
                  dashboard_upload_max_file_mb = %s,
                  dashboard_upload_allowed_mime = %s,
                  llm_primary_backend = %s,
                  llm_smart_routing_enabled = %s,
                  llm_router_model = %s,
                  llm_router_local_confidence_min = %s,
                  llm_router_timeout_sec = %s,
                  llm_route_long_prompt_chars = %s,
                  llm_route_short_local_max_chars = %s,
                  llm_route_many_code_fences = %s,
                  llm_route_many_messages = %s,
                  memory_graph_enabled = %s,
                  memory_graph_max_hops = %s,
                  memory_graph_min_score = %s,
                  memory_graph_max_bullets = %s,
                  memory_graph_max_prompt_chars = %s,
                  memory_graph_log_activations = %s,
                  memory_enabled = %s,
                  rag_enabled = %s,
                  rag_embedding_model = %s,
                  rag_embedding_dim = %s,
                  rag_chunk_size = %s,
                  rag_chunk_overlap = %s,
                  rag_top_k = %s,
                  rag_embed_timeout_sec = %s,
                  rag_tenant_shared_domains = %s,
                  docs_root = %s,
                  pidea_enabled = %s,
                  pidea_cdp_http_url = %s,
                  pidea_selector_ide = %s,
                  pidea_selector_version = %s,
                  expose_internal_errors = %s,
                  http_client_log_level = %s,
                  scheduler_enabled = %s,
                  scheduler_interval_minutes = %s,
                  scheduler_user_id = %s,
                  scheduler_model = %s,
                  scheduler_max_tool_rounds = %s,
                  scheduler_notify_only_if_not_ok = %s,
                  scheduler_max_outbound_per_day = %s,
                  scheduler_allowed_tool_packages = %s,
                  scheduler_llm_backend = %s,
                  scheduler_tools_mode = %s,
                  scheduler_pidea_enabled = %s,
                  scheduler_instructions = %s,
                  scheduler_jobs_worker_enabled = %s,
                  scheduler_jobs_ide_pidea_enabled = %s,
                  scheduler_jobs_ide_pidea_timeout_sec = %s,
                  workspace_allow_self_editing = %s,
                  embedding_api_base_url = %s,
                  embedding_api_key = %s,
                  embedding_api_header_name = %s,
                  rag_embedding_provider_id = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (
                    r.get("discord_application_id"),
                    r.get("integration_notes"),
                    r.get("optional_connection_key"),
                    r.get("agent_mode"),
                    r.get("discord_bot_enabled"),
                    r.get("discord_bot_token"),
                    r.get("discord_bot_agent_bearer"),
                    _discord_trigger_prefix_sql(r),
                    r.get("discord_chat_model"),
                    r.get("telegram_application_id"),
                    r.get("telegram_bot_enabled"),
                    r.get("telegram_bot_token"),
                    r.get("telegram_bot_agent_bearer"),
                    _telegram_trigger_prefix_sql(r),
                    r.get("telegram_chat_model"),
                    r.get("dashboard_upload_max_file_mb"),
                    r.get("dashboard_upload_allowed_mime"),
                    normalize_llm_primary_backend(r.get("llm_primary_backend")),
                    bool(r.get("llm_smart_routing_enabled")),
                    _router_model_from_row(r),
                    _bound_float(r.get("llm_router_local_confidence_min"), 0.7, 0.0, 1.0),
                    _bound_float(r.get("llm_router_timeout_sec"), 12.0, 1.0, 120.0),
                    _bound_int(r.get("llm_route_long_prompt_chars"), 8000, 100, 500_000),
                    _bound_int(r.get("llm_route_short_local_max_chars"), 220, 1, 50_000),
                    _bound_int(r.get("llm_route_many_code_fences"), 3, 1, 100),
                    _bound_int(r.get("llm_route_many_messages"), 14, 1, 500),
                    bool(r.get("memory_graph_enabled", True)),
                    _bound_int(r.get("memory_graph_max_hops"), 2, 0, 4),
                    _bound_float(r.get("memory_graph_min_score"), 0.03, 0.0, 1.0),
                    _bound_int(r.get("memory_graph_max_bullets"), 14, 1, 50),
                    _bound_int(r.get("memory_graph_max_prompt_chars"), 3500, 200, 50_000),
                    bool(r.get("memory_graph_log_activations", False)),
                    bool(r.get("memory_enabled", True)),
                    bool(r.get("rag_enabled", True)),
                    _rag_embedding_model_from_row(r),
                    _coerce_rag_embedding_dim(r.get("rag_embedding_dim")),
                    _bound_int(r.get("rag_chunk_size"), 1200, 200, 8000),
                    _bound_int(r.get("rag_chunk_overlap"), 200, 0, 2000),
                    _bound_int(r.get("rag_top_k"), 8, 1, 50),
                    _bound_float(r.get("rag_embed_timeout_sec"), 120.0, 5.0, 600.0),
                    (
                        str(r.get("rag_tenant_shared_domains"))
                        if r.get("rag_tenant_shared_domains") is not None
                        else "agentlayer_docs"
                    ),
                    r.get("docs_root"),
                    bool(r.get("pidea_enabled", False)),
                    r.get("pidea_cdp_http_url"),
                    r.get("pidea_selector_ide"),
                    r.get("pidea_selector_version"),
                    bool(r.get("expose_internal_errors", False)),
                    _normalize_http_client_log_level_str(r.get("http_client_log_level")),
                    bool(r.get("scheduler_enabled", False)),
                    _bound_int(r.get("scheduler_interval_minutes"), 60, 5, 24 * 60),
                    r.get("scheduler_user_id"),
                    r.get("scheduler_model"),
                    r.get("scheduler_max_tool_rounds"),
                    bool(r.get("scheduler_notify_only_if_not_ok", True)),
                    _bound_int(r.get("scheduler_max_outbound_per_day"), 10, 0, 100_000),
                    r.get("scheduler_allowed_tool_packages"),
                    normalize_scheduler_llm_backend(r.get("scheduler_llm_backend")),
                    normalize_scheduler_tools_mode(r.get("scheduler_tools_mode")),
                    bool(r.get("scheduler_pidea_enabled", False)),
                    r.get("scheduler_instructions"),
                    bool(r.get("scheduler_jobs_worker_enabled", True)),
                    bool(r.get("scheduler_jobs_ide_pidea_enabled", True)),
                    _bound_float(r.get("scheduler_jobs_ide_pidea_timeout_sec"), 300.0, 30.0, 900.0),
                    bool(r.get("workspace_allow_self_editing", False)),
                    r.get("embedding_api_base_url"),
                    r.get("embedding_api_key"),
                    r.get("embedding_api_header_name"),
                    r.get("rag_embedding_provider_id"),
                ),
            )
            extra_sets: list[str] = []
            extra_params: list[Any] = []
            if "workspace_index_on_write_default" in patch:
                extra_sets.append("workspace_index_on_write_default = %s")
                extra_params.append(r.get("workspace_index_on_write_default", "debounced"))
            if "workspace_reindex_after_git_pull" in patch:
                extra_sets.append("workspace_reindex_after_git_pull = %s")
                extra_params.append(bool(r.get("workspace_reindex_after_git_pull", False)))
            if "workspace_nightly_reindex_enabled" in patch:
                extra_sets.append("workspace_nightly_reindex_enabled = %s")
                extra_params.append(bool(r.get("workspace_nightly_reindex_enabled", False)))
            if "workspace_index_on_attach_enabled" in patch:
                extra_sets.append("workspace_index_on_attach_enabled = %s")
                extra_params.append(bool(r.get("workspace_index_on_attach_enabled", False)))
            if "llm_queue_policy" in patch:
                extra_sets.append("llm_queue_policy = %s")
                extra_params.append(str(r.get("llm_queue_policy") or "priority"))
            if "llm_router_model_catalog_owned_by" in patch:
                extra_sets.append("llm_router_model_catalog_owned_by = %s")
                extra_params.append(r.get("llm_router_model_catalog_owned_by"))
            if "llm_queue_user_priority" in patch:
                extra_sets.append("llm_queue_user_priority = %s")
                extra_params.append(int(r.get("llm_queue_user_priority") or 100))
            if "llm_queue_benchmark_priority" in patch:
                extra_sets.append("llm_queue_benchmark_priority = %s")
                extra_params.append(int(r.get("llm_queue_benchmark_priority") or 10))
            if "llm_queue_scheduler_priority" in patch:
                extra_sets.append("llm_queue_scheduler_priority = %s")
                extra_params.append(int(r.get("llm_queue_scheduler_priority") or 50))
            if "delegate_enabled" in patch:
                extra_sets.append("delegate_enabled = %s")
                extra_params.append(bool(r.get("delegate_enabled", True)))
            if "deployment_mode" in patch:
                extra_sets.append("deployment_mode = %s")
                extra_params.append(str(r.get("deployment_mode") or "multi_tenant"))
            if "extractor_api_base_url" in patch:
                extra_sets.append("extractor_api_base_url = %s")
                extra_params.append(r.get("extractor_api_base_url"))
            if "extractor_api_key" in patch:
                extra_sets.append("extractor_api_key = %s")
                extra_params.append(r.get("extractor_api_key"))
            if "extractor_api_header_name" in patch:
                extra_sets.append("extractor_api_header_name = %s")
                extra_params.append(r.get("extractor_api_header_name"))
            if "extractor_provider_id" in patch:
                extra_sets.append("extractor_provider_id = %s")
                extra_params.append(r.get("extractor_provider_id"))
            if "extractor_model" in patch:
                extra_sets.append("extractor_model = %s")
                extra_params.append(r.get("extractor_model"))
            if "extractor_timeout_sec" in patch:
                extra_sets.append("extractor_timeout_sec = %s")
                extra_params.append(_bound_float(r.get("extractor_timeout_sec"), 120.0, 1.0, 1800.0))
            if "discord_chat_model_catalog_owned_by" in patch:
                extra_sets.append("discord_chat_model_catalog_owned_by = %s")
                extra_params.append(r.get("discord_chat_model_catalog_owned_by"))
            if "telegram_chat_model_catalog_owned_by" in patch:
                extra_sets.append("telegram_chat_model_catalog_owned_by = %s")
                extra_params.append(r.get("telegram_chat_model_catalog_owned_by"))
            if "legal_enabled" in patch:
                extra_sets.append("legal_enabled = %s")
                extra_params.append(bool(r.get("legal_enabled", False)))
            if "legal_jurisdiction" in patch:
                extra_sets.append("legal_jurisdiction = %s")
                extra_params.append(str(r.get("legal_jurisdiction") or "none"))
            if "legal_entity_name" in patch:
                extra_sets.append("legal_entity_name = %s")
                extra_params.append(r.get("legal_entity_name"))
            if "legal_entity_address" in patch:
                extra_sets.append("legal_entity_address = %s")
                extra_params.append(r.get("legal_entity_address"))
            if "legal_entity_email" in patch:
                extra_sets.append("legal_entity_email = %s")
                extra_params.append(r.get("legal_entity_email"))
            if "legal_entity_phone" in patch:
                extra_sets.append("legal_entity_phone = %s")
                extra_params.append(r.get("legal_entity_phone"))
            if "legal_terms_enabled" in patch:
                extra_sets.append("legal_terms_enabled = %s")
                extra_params.append(bool(r.get("legal_terms_enabled", False)))
            if "legal_impressum_md" in patch:
                extra_sets.append("legal_impressum_md = %s")
                extra_params.append(r.get("legal_impressum_md"))
            if "legal_privacy_md" in patch:
                extra_sets.append("legal_privacy_md = %s")
                extra_params.append(r.get("legal_privacy_md"))
            if "legal_terms_md" in patch:
                extra_sets.append("legal_terms_md = %s")
                extra_params.append(r.get("legal_terms_md"))
            if extra_sets:
                # SECURITY: Column names in `extra_sets` come from the known
                # _SETTING_KEYS mapping (see _OPERATOR_SETTINGS_KEYS).
                # All values are parameterized via %s placeholders.
                cur.execute(
                    "UPDATE operator_settings SET " + ', '.join(extra_sets) + ", updated_at = now() WHERE id = 1",
                    tuple(extra_params),
                )
            conn.commit()
    if any(
        k in patch
        for k in (
            "embedding_api_base_url",
            "embedding_api_key",
            "embedding_api_header_name",
            "rag_embedding_model",
        )
    ):
        _sync_single_provider_endpoint(
            "embedding",
            label="Embedding provider",
            base_url=r.get("embedding_api_base_url"),
            api_key=r.get("embedding_api_key"),
            api_header_name=r.get("embedding_api_header_name") or "X-API-KEY",
            model_default=r.get("rag_embedding_model"),
        )
    if any(
        k in patch
        for k in (
            "extractor_api_base_url",
            "extractor_api_key",
            "extractor_api_header_name",
            "extractor_model",
            "extractor_timeout_sec",
        )
    ):
        _sync_single_provider_endpoint(
            "extractor",
            label="Extractor provider",
            base_url=r.get("extractor_api_base_url"),
            api_key=r.get("extractor_api_key"),
            api_header_name=r.get("extractor_api_header_name") or "X-API-KEY",
            model_default=r.get("extractor_model"),
            options_json={
                "timeout_sec": _bound_float(r.get("extractor_timeout_sec"), 120.0, 1.0, 1800.0)
            },
        )
    if media_patch:
        from apps.backend.infrastructure.media.operator_media_settings import apply_media_operator_patch

        apply_media_operator_patch(media_patch)
    voice_patch = {
        k: patch[k]
        for k in (
            "voice_enabled",
            "voice_provider_id",
            "voice_stt_provider_id",
            "voice_tts_provider_id",
            "voice_api_base_url",
            "voice_api_key",
            "voice_stt_model",
            "voice_tts_model",
            "voice_tts_voice",
            "voice_max_seconds",
            "voice_max_bytes",
            "voice_bridge_telegram",
            "voice_bridge_discord",
            "voice_realtime_enabled",
            "voice_discord_vc_enabled",
        )
        if k in patch
    }
    if voice_patch:
        from apps.backend.infrastructure.settings.operator_voice_settings_service import apply_voice_operator_patch

        apply_voice_operator_patch(voice_patch)
