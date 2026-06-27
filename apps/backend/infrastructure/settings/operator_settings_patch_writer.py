"""PATCH writer for operator settings."""
from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import (
    _bound_float,
    _bound_int,
    _cached_row,
    _coerce_rag_embedding_dim,
    _discord_trigger_prefix_sql,
    _fetch_row,
    _invalidate,
    _normalize_http_client_log_level_str,
    _normalize_rag_embedding_model,
    _rag_embedding_dim_from_row,
    _sync_single_provider_endpoint,
    _telegram_trigger_prefix_sql,
    logger,
    normalize_model_catalog_owned_by,
    normalize_scheduler_llm_backend,
    normalize_scheduler_tools_mode,
)
from apps.backend.infrastructure.settings.operator_settings_forms import OperatorSettingsPatch

def _maybe_align_pgvector_embedding_dim(r: dict[str, Any], patch: dict[str, Any]) -> None:
    """Migrate pgvector columns when embedding model/dim changes in operator settings."""
    if "rag_embedding_dim" not in patch and "rag_embedding_model" not in patch:
        return
    if not (r.get("rag_embedding_model") or "").strip():
        return
    target = _rag_embedding_dim_from_row(r)
    if target < 32:
        return
    try:
        from apps.backend.infrastructure.providers.pgvector_embedding_dim import ensure_pgvector_embedding_dim

        ensure_pgvector_embedding_dim(target, log_prefix="operator_settings")
    except Exception as e:
        logger.warning("operator_settings: pgvector dim alignment failed: %s", e)


def apply_operator_settings_patch(body: OperatorSettingsPatch) -> None:
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return
    r = _fetch_row()
    if "discord_application_id" in patch:
        v = patch["discord_application_id"]
        r["discord_application_id"] = (v or "").strip() or None
    if "integration_notes" in patch:
        v = patch["integration_notes"]
        r["integration_notes"] = (v or "").strip() or None
    if "discord_bot_enabled" in patch:
        r["discord_bot_enabled"] = bool(patch["discord_bot_enabled"])
    if "discord_bot_token" in patch:
        v = patch["discord_bot_token"]
        if v is None:
            r["discord_bot_token"] = None
        else:
            s = str(v).strip()
            if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
                s = s[1:-1].strip()
            s = "".join(s.split())
            r["discord_bot_token"] = s or None
    if "discord_trigger_prefix" in patch:
        v = patch["discord_trigger_prefix"]
        if v is None:
            r["discord_trigger_prefix"] = "!agent "
        else:
            tp = str(v).strip()[:64]
            if tp and not tp.endswith(" "):
                tp = tp + " "
            r["discord_trigger_prefix"] = tp
    if "discord_chat_model" in patch:
        v = patch["discord_chat_model"]
        r["discord_chat_model"] = None if v is None else (str(v).strip() or None)
    if "discord_chat_model_catalog_owned_by" in patch:
        r["discord_chat_model_catalog_owned_by"] = normalize_model_catalog_owned_by(
            patch["discord_chat_model_catalog_owned_by"]
        )
    if "telegram_bot_enabled" in patch:
        r["telegram_bot_enabled"] = bool(patch["telegram_bot_enabled"])
    if "telegram_bot_token" in patch:
        v = patch["telegram_bot_token"]
        if v is None:
            r["telegram_bot_token"] = None
        else:
            s = str(v).strip()
            if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
                s = s[1:-1].strip()
            s = "".join(s.split())
            r["telegram_bot_token"] = s or None
    if "telegram_trigger_prefix" in patch:
        v = patch["telegram_trigger_prefix"]
        if v is None:
            r["telegram_trigger_prefix"] = "!agent "
        else:
            tp = str(v).strip()[:64]
            if tp and not tp.endswith(" "):
                tp = tp + " "
            r["telegram_trigger_prefix"] = tp
    if "telegram_chat_model" in patch:
        v = patch["telegram_chat_model"]
        r["telegram_chat_model"] = None if v is None else (str(v).strip() or None)
    if "telegram_chat_model_catalog_owned_by" in patch:
        r["telegram_chat_model_catalog_owned_by"] = normalize_model_catalog_owned_by(
            patch["telegram_chat_model_catalog_owned_by"]
        )
    if "dashboard_upload_max_file_mb" in patch:
        v = patch["dashboard_upload_max_file_mb"]
        if v is None:
            r["dashboard_upload_max_file_mb"] = None
        else:
            try:
                mb = int(v)
                r["dashboard_upload_max_file_mb"] = mb if mb > 0 else None
            except (TypeError, ValueError):
                r["dashboard_upload_max_file_mb"] = None
    if "dashboard_upload_allowed_mime" in patch:
        v = patch["dashboard_upload_allowed_mime"]
        if v is None:
            r["dashboard_upload_allowed_mime"] = None
        else:
            s = str(v).strip()
            r["dashboard_upload_allowed_mime"] = s or None
    if "llm_smart_routing_enabled" in patch:
        r["llm_smart_routing_enabled"] = bool(patch["llm_smart_routing_enabled"])
    if "llm_router_model" in patch:
        v = patch["llm_router_model"]
        r["llm_router_model"] = (str(v).strip()[:128] if v is not None else "") or None
    if "llm_router_model_catalog_owned_by" in patch:
        r["llm_router_model_catalog_owned_by"] = normalize_model_catalog_owned_by(
            patch["llm_router_model_catalog_owned_by"]
        )
    if "llm_router_local_confidence_min" in patch:
        v = patch["llm_router_local_confidence_min"]
        r["llm_router_local_confidence_min"] = _bound_float(v, 0.7, 0.0, 1.0) if v is not None else 0.7
    if "llm_router_timeout_sec" in patch:
        v = patch["llm_router_timeout_sec"]
        r["llm_router_timeout_sec"] = _bound_float(v, 12.0, 1.0, 120.0) if v is not None else 12.0
    if "llm_route_long_prompt_chars" in patch:
        v = patch["llm_route_long_prompt_chars"]
        r["llm_route_long_prompt_chars"] = _bound_int(v, 8000, 100, 500_000) if v is not None else 8000
    if "llm_route_short_local_max_chars" in patch:
        v = patch["llm_route_short_local_max_chars"]
        r["llm_route_short_local_max_chars"] = _bound_int(v, 220, 1, 50_000) if v is not None else 220
    if "llm_route_many_code_fences" in patch:
        v = patch["llm_route_many_code_fences"]
        r["llm_route_many_code_fences"] = _bound_int(v, 3, 1, 100) if v is not None else 3
    if "llm_route_many_messages" in patch:
        v = patch["llm_route_many_messages"]
        r["llm_route_many_messages"] = _bound_int(v, 14, 1, 500) if v is not None else 14
    if "llm_queue_policy" in patch:
        v = str(patch["llm_queue_policy"] or "priority").strip().lower()
        r["llm_queue_policy"] = v if v in ("fifo", "priority", "round_robin") else "priority"
    if "llm_queue_user_priority" in patch:
        v = patch["llm_queue_user_priority"]
        r["llm_queue_user_priority"] = _bound_int(v, 100, 0, 1000) if v is not None else 100
    if "llm_queue_benchmark_priority" in patch:
        v = patch["llm_queue_benchmark_priority"]
        r["llm_queue_benchmark_priority"] = _bound_int(v, 10, 0, 1000) if v is not None else 10
    if "llm_queue_scheduler_priority" in patch:
        v = patch["llm_queue_scheduler_priority"]
        r["llm_queue_scheduler_priority"] = _bound_int(v, 50, 0, 1000) if v is not None else 50
    if "delegate_enabled" in patch:
        r["delegate_enabled"] = bool(patch["delegate_enabled"])
    if "memory_graph_enabled" in patch:
        r["memory_graph_enabled"] = bool(patch["memory_graph_enabled"])
    if "memory_graph_max_hops" in patch:
        v = patch["memory_graph_max_hops"]
        r["memory_graph_max_hops"] = _bound_int(v, 2, 0, 4) if v is not None else 2
    if "memory_graph_min_score" in patch:
        v = patch["memory_graph_min_score"]
        r["memory_graph_min_score"] = _bound_float(v, 0.03, 0.0, 1.0) if v is not None else 0.03
    if "memory_graph_max_bullets" in patch:
        v = patch["memory_graph_max_bullets"]
        r["memory_graph_max_bullets"] = _bound_int(v, 14, 1, 50) if v is not None else 14
    if "memory_graph_max_prompt_chars" in patch:
        v = patch["memory_graph_max_prompt_chars"]
        r["memory_graph_max_prompt_chars"] = _bound_int(v, 3500, 200, 50_000) if v is not None else 3500
    if "memory_graph_log_activations" in patch:
        r["memory_graph_log_activations"] = bool(patch["memory_graph_log_activations"])
    if "memory_enabled" in patch:
        r["memory_enabled"] = bool(patch["memory_enabled"])
    if "rag_enabled" in patch:
        r["rag_enabled"] = bool(patch["rag_enabled"])
    if "embedding_api_base_url" in patch:
        v = patch["embedding_api_base_url"]
        if v is None or not str(v).strip():
            r["embedding_api_base_url"] = None
        else:
            r["embedding_api_base_url"] = (
                normalize_external_llm_base_url(str(v).strip()) or str(v).strip()
            )[:2048]
    if "embedding_api_key" in patch:
        v = patch["embedding_api_key"]
        if v is None:
            r["embedding_api_key"] = None
        else:
            s = str(v).strip()
            if s:
                r["embedding_api_key"] = s
    if "embedding_api_header_name" in patch:
        v = patch["embedding_api_header_name"]
        if v is None or not str(v).strip():
            r["embedding_api_header_name"] = None
        else:
            r["embedding_api_header_name"] = str(v).strip()[:128]
    if "rag_embedding_provider_id" in patch:
        v = patch["rag_embedding_provider_id"]
        if v is None or not str(v).strip():
            r["rag_embedding_provider_id"] = None
        else:
            r["rag_embedding_provider_id"] = str(v).strip()[:64]
    if "rag_embedding_model" in patch:
        r["rag_embedding_model"] = _normalize_rag_embedding_model(patch["rag_embedding_model"])
    if "rag_embedding_dim" in patch:
        v = patch["rag_embedding_dim"]
        r["rag_embedding_dim"] = _coerce_rag_embedding_dim(v) if v is not None else 0
    elif "rag_embedding_model" in patch and (r.get("rag_embedding_model") or "").strip():
        try:
            from apps.backend.infrastructure.providers.embedding_client import probe_embedding_output_dim

            probed = probe_embedding_output_dim(model_id=r["rag_embedding_model"])
            r["rag_embedding_dim"] = _coerce_rag_embedding_dim(probed)
            logger.info(
                "operator_settings: rag_embedding_dim auto-synced to %s for model %r",
                r["rag_embedding_dim"],
                r["rag_embedding_model"],
            )
        except Exception as e:
            logger.warning(
                "operator_settings: rag_embedding_dim auto-sync failed for model %r: %s",
                r.get("rag_embedding_model"),
                e,
            )
    if "rag_chunk_size" in patch:
        v = patch["rag_chunk_size"]
        r["rag_chunk_size"] = _bound_int(v, 1200, 200, 8000) if v is not None else 1200
    if "rag_chunk_overlap" in patch:
        v = patch["rag_chunk_overlap"]
        r["rag_chunk_overlap"] = _bound_int(v, 200, 0, 2000) if v is not None else 200
    if "rag_top_k" in patch:
        v = patch["rag_top_k"]
        r["rag_top_k"] = _bound_int(v, 8, 1, 50) if v is not None else 8
    if "rag_embed_timeout_sec" in patch:
        v = patch["rag_embed_timeout_sec"]
        r["rag_embed_timeout_sec"] = _bound_float(v, 120.0, 5.0, 600.0) if v is not None else 120.0
    if "rag_tenant_shared_domains" in patch:
        v = patch["rag_tenant_shared_domains"]
        if v is None:
            r["rag_tenant_shared_domains"] = "agentlayer_docs"
        else:
            r["rag_tenant_shared_domains"] = str(v).strip()
    if "docs_root" in patch:
        v = patch["docs_root"]
        if v is None:
            r["docs_root"] = None
        else:
            s = str(v).strip()
            r["docs_root"] = s or None
    if "pidea_enabled" in patch:
        r["pidea_enabled"] = bool(patch["pidea_enabled"])
    if "pidea_cdp_http_url" in patch:
        v = patch["pidea_cdp_http_url"]
        r["pidea_cdp_http_url"] = None if v is None else (str(v).strip() or None)
    if "pidea_selector_ide" in patch:
        v = patch["pidea_selector_ide"]
        r["pidea_selector_ide"] = None if v is None else (str(v).strip().lower()[:32] or None)
    if "pidea_selector_version" in patch:
        v = patch["pidea_selector_version"]
        r["pidea_selector_version"] = None if v is None else (str(v).strip()[:64] or None)
    if "expose_internal_errors" in patch:
        r["expose_internal_errors"] = bool(patch["expose_internal_errors"])
    if "http_client_log_level" in patch:
        v = patch["http_client_log_level"]
        if v is None:
            r["http_client_log_level"] = "WARNING"
        else:
            r["http_client_log_level"] = _normalize_http_client_log_level_str(v)
    if "scheduler_enabled" in patch:
        r["scheduler_enabled"] = bool(patch["scheduler_enabled"])
    if "scheduler_interval_minutes" in patch:
        v = patch["scheduler_interval_minutes"]
        r["scheduler_interval_minutes"] = _bound_int(v, 60, 5, 24 * 60) if v is not None else 60
    if "scheduler_user_id" in patch:
        v = patch["scheduler_user_id"]
        if v is None or (isinstance(v, str) and not v.strip()):
            r["scheduler_user_id"] = None
        else:
            try:
                r["scheduler_user_id"] = uuid.UUID(str(v).strip())
            except (ValueError, TypeError):
                r["scheduler_user_id"] = None
    if "scheduler_model" in patch:
        v = patch["scheduler_model"]
        r["scheduler_model"] = None if v is None else (str(v).strip() or None)
    if "scheduler_max_tool_rounds" in patch:
        v = patch["scheduler_max_tool_rounds"]
        if v is None:
            r["scheduler_max_tool_rounds"] = None
        else:
            r["scheduler_max_tool_rounds"] = _bound_int(v, 4, 1, 64)
    if "scheduler_notify_only_if_not_ok" in patch:
        r["scheduler_notify_only_if_not_ok"] = bool(patch["scheduler_notify_only_if_not_ok"])
    if "scheduler_max_outbound_per_day" in patch:
        v = patch["scheduler_max_outbound_per_day"]
        r["scheduler_max_outbound_per_day"] = _bound_int(v, 10, 0, 100_000) if v is not None else 10
    if "scheduler_allowed_tool_packages" in patch:
        v = patch["scheduler_allowed_tool_packages"]
        r["scheduler_allowed_tool_packages"] = None if v is None else str(v).strip()
    if "scheduler_llm_backend" in patch:
        v = patch["scheduler_llm_backend"]
        r["scheduler_llm_backend"] = normalize_scheduler_llm_backend(v)
    if "scheduler_tools_mode" in patch:
        v = patch["scheduler_tools_mode"]
        r["scheduler_tools_mode"] = normalize_scheduler_tools_mode(v)
    if "scheduler_pidea_enabled" in patch:
        r["scheduler_pidea_enabled"] = bool(patch["scheduler_pidea_enabled"])
    if "scheduler_instructions" in patch:
        v = patch["scheduler_instructions"]
        r["scheduler_instructions"] = None if v is None else (str(v).strip() or None)
    if "scheduler_jobs_worker_enabled" in patch:
        r["scheduler_jobs_worker_enabled"] = bool(patch["scheduler_jobs_worker_enabled"])
    if "scheduler_jobs_ide_pidea_enabled" in patch:
        r["scheduler_jobs_ide_pidea_enabled"] = bool(patch["scheduler_jobs_ide_pidea_enabled"])
    if "scheduler_jobs_ide_pidea_timeout_sec" in patch:
        v = patch["scheduler_jobs_ide_pidea_timeout_sec"]
        r["scheduler_jobs_ide_pidea_timeout_sec"] = (
            _bound_float(v, 300.0, 30.0, 900.0) if v is not None else 300.0
        )
    if "workspace_allow_self_editing" in patch:
        r["workspace_allow_self_editing"] = bool(patch["workspace_allow_self_editing"])
    if "workspace_index_on_write_default" in patch:
        from apps.backend.infrastructure.workspace.workspace_index_policy import normalize_index_on_write

        v = normalize_index_on_write(patch["workspace_index_on_write_default"]) or "debounced"
        r["workspace_index_on_write_default"] = v
    if "workspace_reindex_after_git_pull" in patch:
        r["workspace_reindex_after_git_pull"] = bool(patch["workspace_reindex_after_git_pull"])
    if "workspace_nightly_reindex_enabled" in patch:
        r["workspace_nightly_reindex_enabled"] = bool(patch["workspace_nightly_reindex_enabled"])
    if "workspace_index_on_attach_enabled" in patch:
        r["workspace_index_on_attach_enabled"] = bool(patch["workspace_index_on_attach_enabled"])

    media_patch = {
        k: patch[k]
        for k in (
            "media_library_enabled",
            "media_user_upload_enabled",
            "media_sharing_enabled",
            "media_default_user_quota_mb",
            "media_upload_max_file_mb",
            "media_upload_allowed_mime",
            "media_embed_allowed_hosts",
        )
        if k in patch
    }

    from apps.backend.infrastructure.settings.operator_settings_patch_persistence import persist_operator_settings_patch

    persist_operator_settings_patch(r, patch, media_patch)
    _invalidate()
    if any(k in patch for k in ("llm_queue_policy", "llm_queue_user_priority", "llm_queue_benchmark_priority", "llm_queue_scheduler_priority")):
        try:
            from apps.backend.infrastructure.agent_runtime.llm_concurrency import invalidate_llm_concurrency_cache

            invalidate_llm_concurrency_cache()
        except Exception:
            pass
    try:
        from apps.backend.infrastructure.providers.embedding_client import invalidate_embedding_catalog_cache

        invalidate_embedding_catalog_cache()
    except Exception:
        pass
    if "rag_embedding_dim" in patch or "rag_embedding_model" in patch:
        try:
            from apps.backend.infrastructure.codebase.code_index_qdrant import invalidate_code_index_cache

            invalidate_code_index_cache()
        except Exception:
            pass
    try:
        from apps.backend.infrastructure.platform.log_redaction import apply_http_client_log_levels

        apply_http_client_log_levels()
    except Exception:
        logger.debug("apply_http_client_log_levels after operator_settings patch failed", exc_info=True)


