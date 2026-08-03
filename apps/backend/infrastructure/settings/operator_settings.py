"""Persisted operator preferences: integrations, agent execution class, LLM routing, memory, RAG.

New product/runtime toggles should be added here (``operator_settings`` row + PATCH API), not as
new ``AGENT_*`` environment variables — those are legacy for bootstrapping containers and local dev.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from apps.backend.infrastructure.platform import config as app_config
from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings_llm_transport import (
    external_api_headers,
    external_chat_completions_url,
    external_llm_should_failover,
    external_models_list_url,
    llm_chat_transport,
    normalize_external_llm_base_url,
    normalize_model_catalog_owned_by,
    resolve_external_llm_credentials_for_catalog,
)

logger = logging.getLogger(__name__)

_PGVECTOR_DIM_CACHE: tuple[float, int] | None = None
_PGVECTOR_DIM_CACHE_TTL_SEC = 30.0


def _normalize_rag_embedding_model(raw: Any) -> str:
    return (str(raw or "").strip())[:256]


def _rag_embedding_model_from_row(r: dict[str, Any]) -> str:
    return _normalize_rag_embedding_model(r.get("rag_embedding_model"))


def _coerce_rag_embedding_dim(v: Any) -> int:
    """Return a bounded dim from an explicit value, or ``0`` when unset/invalid."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    if 32 <= n <= 4096:
        return n
    return 0


def _invalidate_pgvector_dim_cache() -> None:
    global _PGVECTOR_DIM_CACHE
    _PGVECTOR_DIM_CACHE = None


def _deployment_pgvector_dim_cached() -> int:
    """Live ``vector(N)`` width from Postgres; ``0`` when unknown (cached briefly)."""
    global _PGVECTOR_DIM_CACHE
    now = time.monotonic()
    if (
        _PGVECTOR_DIM_CACHE is not None
        and now - _PGVECTOR_DIM_CACHE[0] <= _PGVECTOR_DIM_CACHE_TTL_SEC
    ):
        return _PGVECTOR_DIM_CACHE[1]
    dim = 0
    try:
        from apps.backend.infrastructure.providers.pgvector_embedding_dim import deployment_pgvector_embedding_dim

        probed = deployment_pgvector_embedding_dim()
        if probed is not None and 32 <= int(probed) <= 4096:
            dim = int(probed)
    except Exception:
        pass
    _PGVECTOR_DIM_CACHE = (now, dim)
    return dim


def _rag_embedding_dim_from_row(r: dict[str, Any]) -> int:
    """
    Effective embedding width: stored operator setting, else live pgvector column, else ``0`` (unset).
    """
    stored = _coerce_rag_embedding_dim(r.get("rag_embedding_dim"))
    if stored >= 32:
        return stored
    pg = _deployment_pgvector_dim_cached()
    return pg if pg >= 32 else 0


_CACHE: tuple[float, dict[str, Any]] | None = None
_TTL_SEC = 2.0


def _invalidate() -> None:
    global _CACHE
    _CACHE = None
    _invalidate_pgvector_dim_cache()
    try:
        from apps.backend.infrastructure.providers.embedding_client import clear_embedding_health_cache

        clear_embedding_health_cache()
    except Exception:
        pass
    try:
        from apps.backend.infrastructure.providers.embedding_catalog_providers import (
            invalidate_embedding_provider_specs_cache,
        )

        invalidate_embedding_provider_specs_cache()
    except Exception:
        pass
    try:
        from apps.backend.infrastructure.providers.extractor_catalog_providers import (
            invalidate_extractor_provider_specs_cache,
        )

        invalidate_extractor_provider_specs_cache()
    except Exception:
        pass


def invalidate_operator_settings_cache() -> None:
    """Call after external LLM endpoint sync (and similar) so cached operator row refreshes."""
    _invalidate()


def normalize_scheduler_llm_backend(raw: Any) -> str:
    s = (str(raw or "inherit")).strip().lower()
    return s if s in ("inherit", "provider", "provider_db") else "inherit"


def normalize_llm_primary_backend(raw: Any) -> str:
    s = (str(raw or "provider")).strip().lower()
    return s if s in ("provider", "provider_db") else "provider"


def scheduler_llm_backend_to_agent_override(backend: str) -> str | None:
    """Map operator scheduler backend to ``chat_completion`` ``agent_llm_backend``."""
    if backend == "inherit":
        return None
    if backend == "provider_db":
        return "provider_db"
    return "provider"


def _router_model_from_row(r: dict[str, Any]) -> str:
    return str(r.get("llm_router_model") or "").strip()[:128]


def normalize_scheduler_tools_mode(raw: Any) -> str:
    s = (str(raw or "none")).strip().lower()
    return s if s in ("none", "allowlist", "full") else "none"


_HTTP_CLIENT_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"})


def _normalize_http_client_log_level_str(raw: Any) -> str:
    s = str(raw or "WARNING").strip().upper()
    return s if s in _HTTP_CLIENT_LOG_LEVELS else "WARNING"


def fetch_operator_settings_row() -> dict[str, Any]:
    """Fresh ``operator_settings`` row (bypasses short TTL cache) for background workers."""
    return _fetch_row()


def _fetch_row() -> dict[str, Any]:
    empty = {
        "discord_application_id": None,
        "integration_notes": None,
        "optional_connection_key": None,
        "agent_mode": None,
        "discord_bot_enabled": False,
        "discord_bot_token": None,
        "discord_bot_agent_bearer": None,
        "discord_trigger_prefix": "!agent ",
        "discord_chat_model": None,
        "discord_chat_model_catalog_owned_by": None,
        "telegram_application_id": None,
        "telegram_bot_enabled": False,
        "telegram_bot_token": None,
        "telegram_bot_agent_bearer": None,
        "telegram_trigger_prefix": "!agent ",
        "telegram_chat_model": None,
        "telegram_chat_model_catalog_owned_by": None,
        "dashboard_upload_max_file_mb": None,
        "dashboard_upload_allowed_mime": None,
        "llm_primary_backend": "provider",
        "llm_smart_routing_enabled": False,
        "llm_router_model": "",
        "llm_router_model_catalog_owned_by": None,
        "llm_router_local_confidence_min": 0.7,
        "llm_router_timeout_sec": 12.0,
        "llm_route_long_prompt_chars": 8000,
        "llm_route_short_local_max_chars": 220,
        "llm_route_many_code_fences": 3,
        "llm_route_many_messages": 14,
        "memory_graph_enabled": True,
        "memory_graph_max_hops": 2,
        "memory_graph_min_score": 0.03,
        "memory_graph_max_bullets": 14,
        "memory_graph_max_prompt_chars": 3500,
        "memory_graph_log_activations": False,
        "memory_enabled": True,
        "rag_enabled": True,
        "rag_embedding_model": "",
        "rag_embedding_dim": 0,
        "rag_chunk_size": 1200,
        "rag_chunk_overlap": 200,
        "rag_top_k": 8,
        "rag_embed_timeout_sec": 120.0,
        "rag_tenant_shared_domains": "agentlayer_docs,tenant_knowledge",
        "embedding_api_base_url": None,
        "embedding_api_key": None,
        "embedding_api_header_name": None,
        "rag_embedding_provider_id": None,
        "rag_docs_ingest_fingerprint": None,
        "docs_root": None,
        "pidea_enabled": False,
        "pidea_cdp_http_url": None,
        "pidea_selector_ide": None,
        "pidea_selector_version": None,
        "expose_internal_errors": False,
        "http_client_log_level": "WARNING",
        "scheduler_enabled": False,
        "scheduler_interval_minutes": 60,
        "scheduler_user_id": None,
        "scheduler_model": None,
        "scheduler_max_tool_rounds": None,
        "scheduler_notify_only_if_not_ok": True,
        "scheduler_max_outbound_per_day": 10,
        "scheduler_allowed_tool_packages": None,
        "scheduler_llm_backend": "inherit",
        "scheduler_tools_mode": "none",
        "scheduler_pidea_enabled": False,
        "scheduler_instructions": None,
        "scheduler_jobs_worker_enabled": True,
        "scheduler_jobs_ide_pidea_enabled": True,
        "scheduler_jobs_ide_pidea_timeout_sec": 300.0,
        "workspace_allow_self_editing": False,
        "workspace_index_on_write_default": "debounced",
        "workspace_reindex_after_git_pull": False,
        "workspace_nightly_reindex_enabled": False,
        "workspace_index_on_attach_enabled": False,
        "llm_queue_policy": "priority",
        "llm_queue_user_priority": 100,
        "llm_queue_benchmark_priority": 10,
        "llm_queue_scheduler_priority": 50,
        "delegate_enabled": True,
        "deployment_mode": "multi_tenant",
        "extractor_api_base_url": None,
        "extractor_api_key": None,
        "extractor_api_header_name": None,
        "extractor_provider_id": None,
        "extractor_model": None,
        "extractor_timeout_sec": 120.0,
        "legal_enabled": False,
        "legal_jurisdiction": "none",
        "legal_entity_name": None,
        "legal_entity_address": None,
        "legal_entity_email": None,
        "legal_entity_phone": None,
        "legal_terms_enabled": False,
        "legal_impressum_md": None,
        "legal_privacy_md": None,
        "legal_terms_md": None,
    }
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT discord_application_id, integration_notes,
                           optional_connection_key, agent_mode,
                           discord_bot_enabled, discord_bot_token, discord_bot_agent_bearer,
                           discord_trigger_prefix, discord_chat_model,
                           telegram_application_id, telegram_bot_enabled, telegram_bot_token,
                           telegram_bot_agent_bearer, telegram_trigger_prefix, telegram_chat_model,
                           dashboard_upload_max_file_mb, dashboard_upload_allowed_mime,
                           llm_primary_backend,
                           llm_smart_routing_enabled, llm_router_model,
                           llm_router_model_catalog_owned_by,
                           llm_router_local_confidence_min, llm_router_timeout_sec,
                           llm_route_long_prompt_chars, llm_route_short_local_max_chars,
                           llm_route_many_code_fences, llm_route_many_messages,
                           memory_graph_enabled, memory_graph_max_hops, memory_graph_min_score,
                           memory_graph_max_bullets, memory_graph_max_prompt_chars,
                           memory_graph_log_activations,
                           memory_enabled, rag_enabled, rag_embedding_model, rag_embedding_dim,
                           rag_chunk_size, rag_chunk_overlap, rag_top_k, rag_embed_timeout_sec,
                           rag_tenant_shared_domains, docs_root,
                           pidea_enabled, pidea_cdp_http_url, pidea_selector_ide, pidea_selector_version,
                           expose_internal_errors, http_client_log_level,
                           scheduler_enabled, scheduler_interval_minutes, scheduler_user_id,
                           scheduler_model, scheduler_max_tool_rounds, scheduler_notify_only_if_not_ok,
                           scheduler_max_outbound_per_day, scheduler_allowed_tool_packages,
                           scheduler_llm_backend, scheduler_tools_mode, scheduler_pidea_enabled,
                           scheduler_instructions,
                           scheduler_jobs_worker_enabled, scheduler_jobs_ide_pidea_enabled,
                           scheduler_jobs_ide_pidea_timeout_sec,
                           workspace_allow_self_editing,
                           embedding_api_base_url,
                           embedding_api_key,
                           embedding_api_header_name,
                           rag_embedding_provider_id,
                           rag_docs_ingest_fingerprint,
                           workspace_index_on_write_default,
                           workspace_reindex_after_git_pull,
                           workspace_nightly_reindex_enabled,
                           workspace_index_on_attach_enabled,
                           llm_queue_policy,
                           llm_queue_user_priority,
                           llm_queue_benchmark_priority,
                           llm_queue_scheduler_priority,
                           delegate_enabled,
                           extractor_api_base_url,
                           extractor_api_key,
                           extractor_api_header_name,
                           extractor_provider_id,
                           extractor_model,
                           extractor_timeout_sec,
                           discord_chat_model_catalog_owned_by,
                           telegram_chat_model_catalog_owned_by,
                           deployment_mode,
                           legal_enabled, legal_jurisdiction,
                           legal_entity_name, legal_entity_address,
                           legal_entity_email, legal_entity_phone,
                           legal_terms_enabled,
                           legal_impressum_md, legal_privacy_md, legal_terms_md
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        return dict(empty)
    if not row:
        return dict(empty)
    return {
        "discord_application_id": row[0],
        "integration_notes": row[1],
        "optional_connection_key": row[2],
        "agent_mode": row[3],
        "discord_bot_enabled": bool(row[4]) if row[4] is not None else False,
        "discord_bot_token": row[5],
        "discord_bot_agent_bearer": row[6],
        "discord_trigger_prefix": (
            str(row[7]).strip()[:64] if row[7] is not None else "!agent "
        ),
        "discord_chat_model": row[8],
        "telegram_application_id": row[9],
        "telegram_bot_enabled": bool(row[10]) if row[10] is not None else False,
        "telegram_bot_token": row[11],
        "telegram_bot_agent_bearer": row[12],
        "telegram_trigger_prefix": (
            str(row[13]).strip()[:64] if row[13] is not None else "!agent "
        ),
        "telegram_chat_model": row[14],
        "dashboard_upload_max_file_mb": row[15],
        "dashboard_upload_allowed_mime": row[16],
        "llm_primary_backend": normalize_llm_primary_backend(row[17] if row[17] is not None else None),
        "llm_smart_routing_enabled": bool(row[18]) if row[18] is not None else False,
        "llm_router_model": (str(row[19]).strip() if row[19] is not None else "")[:128],
        "llm_router_model_catalog_owned_by": normalize_model_catalog_owned_by(row[20]),
        "llm_router_local_confidence_min": float(row[21]) if row[21] is not None else 0.7,
        "llm_router_timeout_sec": float(row[22]) if row[22] is not None else 12.0,
        "llm_route_long_prompt_chars": int(row[23]) if row[23] is not None else 8000,
        "llm_route_short_local_max_chars": int(row[24]) if row[24] is not None else 220,
        "llm_route_many_code_fences": int(row[25]) if row[25] is not None else 3,
        "llm_route_many_messages": int(row[26]) if row[26] is not None else 14,
        "memory_graph_enabled": bool(row[27]) if row[27] is not None else True,
        "memory_graph_max_hops": int(row[28]) if row[28] is not None else 2,
        "memory_graph_min_score": float(row[29]) if row[29] is not None else 0.03,
        "memory_graph_max_bullets": int(row[30]) if row[30] is not None else 14,
        "memory_graph_max_prompt_chars": int(row[31]) if row[31] is not None else 3500,
        "memory_graph_log_activations": bool(row[32]) if row[32] is not None else False,
        "memory_enabled": bool(row[33]) if row[33] is not None else True,
        "rag_enabled": bool(row[34]) if row[34] is not None else True,
        "rag_embedding_model": _normalize_rag_embedding_model(row[35]),
        "rag_embedding_dim": int(row[36]) if row[36] is not None else 0,
        "rag_chunk_size": int(row[37]) if row[37] is not None else 1200,
        "rag_chunk_overlap": int(row[38]) if row[38] is not None else 200,
        "rag_top_k": int(row[39]) if row[39] is not None else 8,
        "rag_embed_timeout_sec": float(row[40]) if row[40] is not None else 120.0,
        "rag_tenant_shared_domains": (
            str(row[41]) if row[41] is not None else "agentlayer_docs"
        ),
        "docs_root": row[42],
        "pidea_enabled": bool(row[43]) if row[43] is not None else False,
        "pidea_cdp_http_url": row[44],
        "pidea_selector_ide": row[45],
        "pidea_selector_version": row[46],
        "expose_internal_errors": bool(row[47]) if row[47] is not None else False,
        "http_client_log_level": _normalize_http_client_log_level_str(row[48]) if len(row) > 48 else "WARNING",
        "scheduler_enabled": bool(row[49]) if len(row) > 49 and row[49] is not None else False,
        "scheduler_interval_minutes": int(row[50]) if len(row) > 50 and row[50] is not None else 60,
        "scheduler_user_id": row[51] if len(row) > 51 else None,
        "scheduler_model": row[52] if len(row) > 52 else None,
        "scheduler_max_tool_rounds": int(row[53]) if len(row) > 53 and row[53] is not None else None,
        "scheduler_notify_only_if_not_ok": bool(row[54]) if len(row) > 54 and row[54] is not None else True,
        "scheduler_max_outbound_per_day": int(row[55]) if len(row) > 55 and row[55] is not None else 10,
        "scheduler_allowed_tool_packages": row[56] if len(row) > 56 else None,
        "scheduler_llm_backend": normalize_scheduler_llm_backend(row[57] if len(row) > 57 else None),
        "scheduler_tools_mode": normalize_scheduler_tools_mode(row[58] if len(row) > 58 else None),
        "scheduler_pidea_enabled": bool(row[59]) if len(row) > 59 and row[59] is not None else False,
        "scheduler_instructions": row[60] if len(row) > 60 else None,
        "scheduler_jobs_worker_enabled": bool(row[61]) if len(row) > 61 and row[61] is not None else True,
        "scheduler_jobs_ide_pidea_enabled": bool(row[62]) if len(row) > 62 and row[62] is not None else True,
        "scheduler_jobs_ide_pidea_timeout_sec": float(row[63])
        if len(row) > 63 and row[63] is not None
        else 300.0,
        "workspace_allow_self_editing": bool(row[64]) if len(row) > 64 and row[64] is not None else False,
        "embedding_api_base_url": (
            (str(row[65]).strip() or None) if len(row) > 65 and row[65] is not None else None
        ),
        "embedding_api_key": (
            (str(row[66]).strip() or None) if len(row) > 66 and row[66] is not None else None
        ),
        "embedding_api_header_name": (
            (str(row[67]).strip() or None) if len(row) > 67 and row[67] is not None else None
        ),
        "rag_embedding_provider_id": (
            (str(row[68]).strip() or None) if len(row) > 68 and row[68] is not None else None
        ),
        "rag_docs_ingest_fingerprint": (
            (str(row[69]).strip() or None) if len(row) > 69 and row[69] is not None else None
        ),
        "workspace_index_on_write_default": (
            str(row[70]).strip().lower()
            if len(row) > 70 and row[70] is not None and str(row[70]).strip()
            else "debounced"
        ),
        "workspace_reindex_after_git_pull": bool(row[71]) if len(row) > 71 and row[71] is not None else False,
        "workspace_nightly_reindex_enabled": bool(row[72]) if len(row) > 72 and row[72] is not None else False,
        "workspace_index_on_attach_enabled": bool(row[73]) if len(row) > 73 and row[73] is not None else False,
        "llm_queue_policy": (
            str(row[74]).strip().lower()
            if len(row) > 74 and row[74] is not None and str(row[74]).strip()
            else "priority"
        ),
        "llm_queue_user_priority": int(row[75]) if len(row) > 75 and row[75] is not None else 100,
        "llm_queue_benchmark_priority": int(row[76]) if len(row) > 76 and row[76] is not None else 10,
        "llm_queue_scheduler_priority": int(row[77]) if len(row) > 77 and row[77] is not None else 50,
        "delegate_enabled": bool(row[78]) if len(row) > 78 and row[78] is not None else True,
        "extractor_api_base_url": (
            (str(row[79]).strip() or None) if len(row) > 79 and row[79] is not None else None
        ),
        "extractor_api_key": (
            (str(row[80]).strip() or None) if len(row) > 80 and row[80] is not None else None
        ),
        "extractor_api_header_name": (
            (str(row[81]).strip() or None) if len(row) > 81 and row[81] is not None else None
        ),
        "extractor_provider_id": (
            (str(row[82]).strip() or None) if len(row) > 82 and row[82] is not None else None
        ),
        "extractor_model": (
            (str(row[83]).strip() or None) if len(row) > 83 and row[83] is not None else None
        ),
        "extractor_timeout_sec": float(row[84]) if len(row) > 84 and row[84] is not None else 120.0,
        "discord_chat_model_catalog_owned_by": normalize_model_catalog_owned_by(row[85] if len(row) > 85 else None),
        "telegram_chat_model_catalog_owned_by": normalize_model_catalog_owned_by(row[86] if len(row) > 86 else None),
        "deployment_mode": (
            str(row[87]).strip().lower()
            if len(row) > 87 and row[87] is not None and str(row[87]).strip().lower() in ("agent_system", "multi_tenant")
            else "multi_tenant"
        ),
        "legal_enabled": bool(row[88]) if len(row) > 88 and row[88] is not None else False,
        "legal_jurisdiction": (
            str(row[89]).strip().lower()
            if len(row) > 89 and row[89] is not None and str(row[89]).strip().lower() in ("none", "de", "en", "custom")
            else "none"
        ),
        "legal_entity_name": (
            (str(row[90]).strip() or None) if len(row) > 90 and row[90] is not None else None
        ),
        "legal_entity_address": (
            (str(row[91]).strip() or None) if len(row) > 91 and row[91] is not None else None
        ),
        "legal_entity_email": (
            (str(row[92]).strip() or None) if len(row) > 92 and row[92] is not None else None
        ),
        "legal_entity_phone": (
            (str(row[93]).strip() or None) if len(row) > 93 and row[93] is not None else None
        ),
        "legal_terms_enabled": bool(row[94]) if len(row) > 94 and row[94] is not None else False,
        "legal_impressum_md": row[95] if len(row) > 95 else None,
        "legal_privacy_md": row[96] if len(row) > 96 else None,
        "legal_terms_md": row[97] if len(row) > 97 else None,
    }


def _cached_row() -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if _CACHE is not None and (now - _CACHE[0]) < _TTL_SEC:
        return dict(_CACHE[1])
    row = _fetch_row()
    _CACHE = (now, row)
    return dict(row)


def _sync_single_provider_endpoint(
    kind: str,
    *,
    label: str,
    base_url: Any,
    api_key: Any,
    api_header_name: Any,
    model_default: Any = None,
    options_json: dict[str, Any] | None = None,
) -> None:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return
    rows = db.operator_provider_endpoints_list_all(kind)
    row: dict[str, Any] = {
        "sort_order": 0,
        "enabled": True,
        "label": label,
        "base_url": base,
        "api_key": str(api_key or "").strip(),
        "api_header_name": str(api_header_name or "").strip() or "Authorization",
        "model_default": (str(model_default).strip() if model_default is not None else None) or None,
        "options_json": options_json or {},
    }
    if rows:
        row["id"] = int(rows[0]["id"])
    db.operator_provider_endpoints_sync(kind, [row], delete_missing=False)


def _bound_int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _bound_float(v: Any, default: float, lo: float, hi: float) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _discord_trigger_prefix_sql(r: dict[str, Any]) -> str:
    raw = str(r.get("discord_trigger_prefix") or "").strip()
    return raw[:16]


def _telegram_trigger_prefix_sql(r: dict[str, Any]) -> str:
    raw = str(r.get("telegram_trigger_prefix") or "").strip()
    return raw[:16]


from apps.backend.infrastructure.settings.operator_settings_readers import (
    code_graph_enabled,
    delegate_enabled,
    deployment_mode,
    effective_dashboard_upload_max_bytes,
    effective_dashboard_upload_mime,
    effective_docs_root_str,
    effective_http_client_log_level_int,
    effective_rag_tenant_shared_domains,
    embedding_api_public_fields,
    expose_internal_errors_in_responses,
    memory_graph_prompt_settings,
    memory_service_enabled,
    pidea_effective_enabled,
    public_dict,
    rag_docs_ingest_fingerprint,
    rag_embedding_ready,
    rag_settings,
    resolved_agent_mode,
    resolved_embedding_api_base_url,
    resolved_embedding_api_header_name,
    resolved_embedding_api_key,
    resolved_primary_llm_backend,
    set_rag_docs_ingest_fingerprint,
    smart_llm_routing_enabled,
    smart_routing_params,
)
from apps.backend.infrastructure.settings.operator_settings_forms import (
    OperatorSettingsPatch,
    OperatorSettingsPayload,
    operator_settings_patch_client_error,
    operator_settings_patch_field_names,
    operator_settings_patch_tool_parameters,
)
from apps.backend.infrastructure.settings.operator_settings_writer import (
    InterfaceHintsPayload,
    apply_interface_hints,
    apply_operator_settings_patch,
    apply_update,
    interface_hints_public,
    scheduler_jobs_worker_settings,
)
