from __future__ import annotations

import logging
import os
from typing import Any, Literal

from apps.backend.infrastructure.platform import config as app_config
from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.settings.operator_settings import (
    _cached_row,
    _invalidate,
    _rag_embedding_dim_from_row,
    _rag_embedding_model_from_row,
    _router_model_from_row,
    normalize_llm_primary_backend,
    normalize_scheduler_llm_backend,
    normalize_scheduler_tools_mode,
)
from apps.backend.infrastructure.settings.operator_settings_llm_transport import normalize_model_catalog_owned_by
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

def delegate_enabled() -> bool:
    """Operator kill-switch for the delegate tool (default true)."""
    return bool(_cached_row().get("delegate_enabled", True))


def deployment_mode() -> str:
    v = str(_cached_row().get("deployment_mode") or "multi_tenant").strip().lower()
    return v if v in ("agent_system", "multi_tenant") else "multi_tenant"


def rag_docs_ingest_fingerprint() -> str:
    """Last successful incremental docs ingest (embedding model/dim + chunking)."""
    return (str(_cached_row().get("rag_docs_ingest_fingerprint") or "").strip())


def set_rag_docs_ingest_fingerprint(value: str) -> None:
    v = (value or "").strip()[:128] or None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operator_settings
                SET rag_docs_ingest_fingerprint = %s, updated_at = now()
                WHERE id = 1
                """,
                (v,),
            )
        conn.commit()
    _invalidate()


def resolved_embedding_api_base_url() -> str:
    from apps.backend.infrastructure.providers.embedding_catalog_providers import resolve_active_embedding_spec

    spec = resolve_active_embedding_spec()
    return spec.base_url.rstrip("/") if spec else ""


def resolved_embedding_api_header_name() -> str:
    from apps.backend.infrastructure.providers.embedding_catalog_providers import resolve_active_embedding_spec

    spec = resolve_active_embedding_spec()
    if spec is not None:
        return spec.api_header_name or "X-API-KEY"
    return "X-API-KEY"


def resolved_embedding_api_key() -> str:
    from apps.backend.infrastructure.providers.embedding_catalog_providers import resolve_active_embedding_spec

    spec = resolve_active_embedding_spec()
    return (spec.api_key or "").strip() if spec else ""


def embedding_api_public_fields() -> dict[str, Any]:
    """Embedding providers + active provider for admin UI (no secrets)."""
    from apps.backend.infrastructure.providers.embedding_catalog_providers import (
        list_embedding_provider_specs,
        resolve_active_embedding_provider_id,
        resolve_active_embedding_spec,
    )

    r = _cached_row()
    db_stored = (str(r.get("embedding_api_base_url") or "").strip() or None)
    specs = list_embedding_provider_specs()
    active_id = resolve_active_embedding_provider_id()
    active = resolve_active_embedding_spec()
    effective = active.base_url.rstrip("/") if active else ""
    env_providers = [s for s in specs if s.source.startswith("env")]
    base_source: str | None = "env" if env_providers else ("operator_settings" if db_stored else None)
    if active and active.source == "operator_settings":
        base_source = "operator_settings"
    elif active and active.source.startswith("env"):
        base_source = "env"

    db_key = (str(r.get("embedding_api_key") or "").strip())
    db_header = (str(r.get("embedding_api_header_name") or "").strip() or None)
    active_key = (active.api_key if active else "") or ""
    key_source: str | None = (
        "env"
        if active and active.source.startswith("env") and active_key
        else ("operator_settings" if db_key else None)
    )
    header_source: str | None = key_source

    db_provider_id = (str(r.get("rag_embedding_provider_id") or "").strip() or None)
    provider_id_source: str | None = "operator_settings" if db_provider_id else None

    return {
        "embedding_api_base_url": db_stored,
        "embedding_api_base_source": base_source,
        "embedding_api_base_effective": effective or None,
        "embedding_api_key_configured": bool(active_key or db_key),
        "embedding_api_key_source": key_source,
        "embedding_api_header_name": db_header,
        "embedding_api_header_name_effective": resolved_embedding_api_header_name(),
        "embedding_api_header_name_source": header_source,
        "rag_embedding_provider_id": db_provider_id,
        "rag_embedding_provider_id_effective": active_id,
        "rag_embedding_provider_id_source": provider_id_source,
        "embedding_providers": [
            {"provider_id": s.provider_id, "label": s.label, "source": s.source, "base_url": s.base_url}
            for s in specs
        ],
    }


def resolved_agent_mode() -> Literal["sandbox", "host"]:
    """DB ``agent_mode`` wins when set; else :envvar:`AGENT_MODE` (default ``sandbox``)."""
    r = _cached_row()
    v = r.get("agent_mode")
    if isinstance(v, str) and v.strip().lower() in ("sandbox", "host"):
        return v.strip().lower()  # type: ignore[return-value]
    em = getattr(config, "AGENT_MODE", "sandbox")
    if isinstance(em, str) and em.strip().lower() in ("sandbox", "host"):
        return em.strip().lower()  # type: ignore[return-value]
    return "sandbox"


def effective_dashboard_upload_max_bytes() -> int:
    """DB override (MB) when set; else ``WORKSPACE_UPLOAD_MAX_FILE_MB`` from env."""
    r = _cached_row()
    v = r.get("dashboard_upload_max_file_mb")
    if v is not None:
        try:
            mb = int(v)
            if mb > 0:
                return mb * 1024 * 1024
        except (TypeError, ValueError):
            pass
    return app_config.WORKSPACE_UPLOAD_MAX_FILE_MB * 1024 * 1024


def resolved_primary_llm_backend() -> Literal["provider", "provider_db"]:
    r = _cached_row()
    return normalize_llm_primary_backend(r.get("llm_primary_backend"))


def smart_llm_routing_enabled() -> bool:
    return bool(_cached_row().get("llm_smart_routing_enabled"))


def _bound_int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def _bound_float(v: Any, default: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, x))


_HTTP_CLIENT_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"})


def _normalize_http_client_log_level_str(raw: Any) -> str:
    s = (str(raw or "WARNING")).strip().upper()
    return s if s in _HTTP_CLIENT_LOG_LEVELS else "WARNING"


def effective_http_client_log_level_int() -> int:
    """``httpx`` / ``httpcore`` level from DB ``http_client_log_level``; on error, ``WARNING``."""
    import logging

    try:
        r = _cached_row()
        s = _normalize_http_client_log_level_str(r.get("http_client_log_level"))
    except Exception:
        return logging.WARNING
    return getattr(logging, s, logging.WARNING)


def smart_routing_params() -> dict[str, Any]:
    r = _cached_row()
    return {
        "router_model": _router_model_from_row(r),
        "router_model_catalog_owned_by": normalize_model_catalog_owned_by(
            r.get("llm_router_model_catalog_owned_by")
        ),
        "local_confidence_min": _bound_float(r.get("llm_router_local_confidence_min"), 0.7, 0.0, 1.0),
        "router_timeout_sec": _bound_float(r.get("llm_router_timeout_sec"), 12.0, 1.0, 120.0),
        "long_prompt_chars": _bound_int(r.get("llm_route_long_prompt_chars"), 8000, 100, 500_000),
        "short_local_max_chars": _bound_int(r.get("llm_route_short_local_max_chars"), 220, 1, 50_000),
        "many_code_fences": _bound_int(r.get("llm_route_many_code_fences"), 3, 1, 100),
        "many_messages": _bound_int(r.get("llm_route_many_messages"), 14, 1, 500),
    }


def memory_graph_prompt_settings() -> dict[str, Any]:
    """Graph memory injection + activation logging (operator_settings / Admin → Interfaces)."""
    r = _cached_row()
    return {
        "enabled": bool(r.get("memory_graph_enabled", True)),
        "max_hops": _bound_int(r.get("memory_graph_max_hops"), 2, 0, 4),
        "min_score": _bound_float(r.get("memory_graph_min_score"), 0.03, 0.0, 1.0),
        "max_bullets": _bound_int(r.get("memory_graph_max_bullets"), 14, 1, 50),
        "max_prompt_chars": _bound_int(r.get("memory_graph_max_prompt_chars"), 3500, 200, 50_000),
        "log_activations": bool(r.get("memory_graph_log_activations", False)),
    }


def memory_service_enabled() -> bool:
    """Facts + semantic notes (and graph when enabled). Admin → Interfaces ``memory_enabled``."""
    return bool(_cached_row().get("memory_enabled", True))


def expose_internal_errors_in_responses() -> bool:
    """When true, some HTTP 5xx ``detail`` may include ``str(exception)`` (debug). Admin → Interfaces."""
    return bool(_cached_row().get("expose_internal_errors", False))


def code_graph_enabled() -> bool:
    """True when Neo4j URL is configured and the driver is importable."""
    url = (os.environ.get("NEO4J_URL") or getattr(app_config, "NEO4J_URL", "")).strip()
    if not url:
        return False
    try:
        import neo4j  # noqa: F401
        return True
    except ImportError:
        return False


def rag_embedding_ready() -> bool:
    """RAG ingest/search need embedding API base and a non-empty model id."""
    if not rag_settings()["enabled"]:
        return False
    try:
        from apps.backend.infrastructure.providers.embedding_client import _normalized_embedding_base

        if not _normalized_embedding_base():
            return False
    except Exception:
        return False
    return bool((rag_settings().get("embedding_model") or "").strip())


def rag_settings() -> dict[str, Any]:
    """RAG chunking, embed model, top_k (operator_settings / Admin → Interfaces)."""
    r = _cached_row()
    return {
        "enabled": bool(r.get("rag_enabled", True)),
        "embedding_model": _rag_embedding_model_from_row(r),
        "embedding_dim": _rag_embedding_dim_from_row(r),
        "chunk_size": _bound_int(r.get("rag_chunk_size"), 1200, 200, 8000),
        "chunk_overlap": _bound_int(r.get("rag_chunk_overlap"), 200, 0, 2000),
        "top_k": _bound_int(r.get("rag_top_k"), 8, 1, 50),
        "embed_timeout_sec": _bound_float(r.get("rag_embed_timeout_sec"), 120.0, 5.0, 600.0),
    }


def effective_rag_tenant_shared_domains() -> frozenset[str]:
    """Comma-separated domain ids; empty string → none; default list includes ``agentlayer_docs``."""
    r = _cached_row()
    raw = r.get("rag_tenant_shared_domains")
    if raw is None:
        return frozenset({"agentlayer_docs"})
    s = str(raw).strip()
    if not s:
        return frozenset()
    return frozenset(x.strip().lower() for x in s.split(",") if x.strip())


def effective_docs_root_str() -> str | None:
    """Optional filesystem root for markdown ingest; None/empty → use repository ``docs/`` in callers."""
    r = _cached_row()
    raw = r.get("docs_root")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


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

def _discord_trigger_prefix_public(r: dict[str, Any]) -> str:
    """DB value for API; empty string means *no prefix* (bridge uses whole message)."""
    v = r.get("discord_trigger_prefix")
    if v is None:
        return "!agent "
    return str(v)[:64]


def _discord_trigger_prefix_sql(r: dict[str, Any]) -> str:
    """Value persisted in ``UPDATE`` (empty string allowed)."""
    v = r.get("discord_trigger_prefix")
    if v is None:
        return "!agent "
    return str(v)[:64]


def _telegram_trigger_prefix_public(r: dict[str, Any]) -> str:
    v = r.get("telegram_trigger_prefix")
    if v is None:
        return "!agent "
    return str(v)[:64]


def _telegram_trigger_prefix_sql(r: dict[str, Any]) -> str:
    v = r.get("telegram_trigger_prefix")
    if v is None:
        return "!agent "
    return str(v)[:64]


def effective_dashboard_upload_mime() -> frozenset[str]:
    """Comma allowlist from DB when set; else env ``AGENT_DASHBOARD_UPLOAD_ALLOWED_MIME``."""
    r = _cached_row()
    raw = r.get("dashboard_upload_allowed_mime")
    if isinstance(raw, str) and raw.strip():
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return app_config.WORKSPACE_upload_env_allowed_mime()


def pidea_effective_enabled() -> bool:
    """DB ``pidea_enabled`` unless :envvar:`AGENT_PIDEA_ENABLED` overrides (true/false)."""
    raw = (os.environ.get("AGENT_PIDEA_ENABLED") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on"):
        return True
    return bool(_cached_row().get("pidea_enabled", False))


# def resolved_pidea_connection_config() -> Any:
#     """``ConnectionConfig`` for PIDEA (DB overrides, sonst ``config``)."""
#     from apps.backend.infrastructure.integrations.pidea.types import ConnectionConfig

#     r = _cached_row()
#     cdp = (
#         str(r.get("pidea_cdp_http_url") or "").strip().rstrip("/")
#         or str(getattr(config, "PIDEA_CDP_HTTP_URL", "") or "").strip().rstrip("/")
#         or "http://0.0.0.0:9222"
#     )
#     ide = (
#         str(r.get("pidea_selector_ide") or "").strip().lower()
#         or str(getattr(config, "PIDEA_SELECTOR_IDE", "cursor") or "").strip().lower()
#     )
#     ver = (
#         str(r.get("pidea_selector_version") or "").strip()
#         or str(getattr(config, "PIDEA_SELECTOR_VERSION", "1.7.17") or "").strip()
#     )
#     timeout = int(getattr(config, "PIDEA_DEFAULT_TIMEOUT_MS", 30_000))
#     return ConnectionConfig(
#         cdp_http_url=cdp,
#         selector_ide=ide,
#         selector_version=ver,
#         default_timeout_ms=timeout,
#     )


def public_dict() -> dict[str, Any]:
    from apps.backend.infrastructure.settings.operator_voice_settings_service import voice_settings_public_fields
    from apps.backend.infrastructure.providers.extractor_catalog_providers import extractor_providers_public_fields
    from apps.backend.infrastructure.media.operator_media_settings import media_settings_public_fields

    r = _cached_row()
    dtok = (r.get("discord_bot_token") or "").strip()
    ttok = (r.get("telegram_bot_token") or "").strip()
    return {
        "identity_policy": (
            "User and tenant are resolved only from Authorization: Bearer (JWT or API key); "
            "tenant is users.tenant_id. No operator-configured identity headers."
        ),
        "discord_application_id": r.get("discord_application_id") or "",
        "integration_notes": r.get("integration_notes") or "",
        "agent_mode": (r.get("agent_mode") or "") if isinstance(r.get("agent_mode"), str) else "",
        "agent_mode_effective": resolved_agent_mode(),
        "agent_mode_env": getattr(config, "AGENT_MODE", "sandbox"),
        "discord_bot_enabled": bool(r.get("discord_bot_enabled")),
        "discord_bot_token_configured": bool(dtok),
        "discord_trigger_prefix": _discord_trigger_prefix_public(r),
        "discord_chat_model": (str(r.get("discord_chat_model") or "").strip())[:256],
        "discord_chat_model_catalog_owned_by": normalize_model_catalog_owned_by(
            r.get("discord_chat_model_catalog_owned_by")
        ),
        "telegram_application_id": r.get("telegram_application_id") or "",
        "telegram_bot_enabled": bool(r.get("telegram_bot_enabled")),
        "telegram_bot_token_configured": bool(ttok),
        "telegram_trigger_prefix": _telegram_trigger_prefix_public(r),
        "telegram_chat_model": (str(r.get("telegram_chat_model") or "").strip())[:256],
        "telegram_chat_model_catalog_owned_by": normalize_model_catalog_owned_by(
            r.get("telegram_chat_model_catalog_owned_by")
        ),
        "dashboard_upload_max_file_mb": r.get("dashboard_upload_max_file_mb"),
        "dashboard_upload_allowed_mime": (r.get("dashboard_upload_allowed_mime") or "").strip(),
        "dashboard_upload_effective_max_bytes": effective_dashboard_upload_max_bytes(),
        "dashboard_upload_effective_allowed_mime": sorted(effective_dashboard_upload_mime()),
        "llm_smart_routing_enabled": bool(r.get("llm_smart_routing_enabled")),
        "llm_router_model": _router_model_from_row(r),
        "llm_router_model_catalog_owned_by": normalize_model_catalog_owned_by(
            r.get("llm_router_model_catalog_owned_by")
        ),
        "llm_router_local_confidence_min": _bound_float(r.get("llm_router_local_confidence_min"), 0.7, 0.0, 1.0),
        "llm_router_timeout_sec": _bound_float(r.get("llm_router_timeout_sec"), 12.0, 1.0, 120.0),
        "llm_route_long_prompt_chars": _bound_int(r.get("llm_route_long_prompt_chars"), 8000, 100, 500_000),
        "llm_route_short_local_max_chars": _bound_int(r.get("llm_route_short_local_max_chars"), 220, 1, 50_000),
        "llm_route_many_code_fences": _bound_int(r.get("llm_route_many_code_fences"), 3, 1, 100),
        "llm_route_many_messages": _bound_int(r.get("llm_route_many_messages"), 14, 1, 500),
        "llm_queue_policy": (
            str(r.get("llm_queue_policy") or "priority").strip().lower()
            if str(r.get("llm_queue_policy") or "priority").strip().lower()
            in ("fifo", "priority", "round_robin")
            else "priority"
        ),
        "llm_queue_user_priority": _bound_int(r.get("llm_queue_user_priority"), 100, 0, 1000),
        "llm_queue_benchmark_priority": _bound_int(r.get("llm_queue_benchmark_priority"), 10, 0, 1000),
        "llm_queue_scheduler_priority": _bound_int(r.get("llm_queue_scheduler_priority"), 50, 0, 1000),
        "delegate_enabled": bool(r.get("delegate_enabled", True)),
        "deployment_mode": deployment_mode(),
        "memory_graph_enabled": bool(r.get("memory_graph_enabled", True)),
        "memory_graph_max_hops": _bound_int(r.get("memory_graph_max_hops"), 2, 0, 4),
        "memory_graph_min_score": _bound_float(r.get("memory_graph_min_score"), 0.03, 0.0, 1.0),
        "memory_graph_max_bullets": _bound_int(r.get("memory_graph_max_bullets"), 14, 1, 50),
        "memory_graph_max_prompt_chars": _bound_int(r.get("memory_graph_max_prompt_chars"), 3500, 200, 50_000),
        "memory_graph_log_activations": bool(r.get("memory_graph_log_activations", False)),
        "memory_enabled": bool(r.get("memory_enabled", True)),
        "rag_enabled": bool(r.get("rag_enabled", True)),
        **embedding_api_public_fields(),
        **extractor_providers_public_fields(),
        "rag_embedding_model": _rag_embedding_model_from_row(r),
        "rag_embedding_dim": _rag_embedding_dim_from_row(r),
        "rag_chunk_size": _bound_int(r.get("rag_chunk_size"), 1200, 200, 8000),
        "rag_chunk_overlap": _bound_int(r.get("rag_chunk_overlap"), 200, 0, 2000),
        "rag_top_k": _bound_int(r.get("rag_top_k"), 8, 1, 50),
        "rag_embed_timeout_sec": _bound_float(r.get("rag_embed_timeout_sec"), 120.0, 5.0, 600.0),
        "rag_tenant_shared_domains": (str(r.get("rag_tenant_shared_domains") or "").strip()),
        "rag_tenant_shared_domains_effective": sorted(effective_rag_tenant_shared_domains()),
        "docs_root": (str(r.get("docs_root") or "").strip()),
        "pidea_enabled": bool(r.get("pidea_enabled", False)),
        "pidea_effective_enabled": pidea_effective_enabled(),
        "pidea_cdp_http_url": (str(r.get("pidea_cdp_http_url") or "").strip()),
        "pidea_selector_ide": (str(r.get("pidea_selector_ide") or "").strip()),
        "pidea_selector_version": (str(r.get("pidea_selector_version") or "").strip()),
        "expose_internal_errors": bool(r.get("expose_internal_errors", False)),
        "http_client_log_level": _normalize_http_client_log_level_str(r.get("http_client_log_level")),
        "scheduler_enabled": bool(r.get("scheduler_enabled", False)),
        "scheduler_interval_minutes": _bound_int(r.get("scheduler_interval_minutes"), 60, 5, 24 * 60),
        "scheduler_user_id": str(r.get("scheduler_user_id")).strip()
        if r.get("scheduler_user_id") is not None
        else "",
        "scheduler_model": (str(r.get("scheduler_model") or "").strip() or None),
        "scheduler_max_tool_rounds": r.get("scheduler_max_tool_rounds"),
        "scheduler_notify_only_if_not_ok": bool(r.get("scheduler_notify_only_if_not_ok", True)),
        "scheduler_max_outbound_per_day": _bound_int(r.get("scheduler_max_outbound_per_day"), 10, 0, 10_000),
        "scheduler_allowed_tool_packages": (str(r.get("scheduler_allowed_tool_packages") or "").strip()),
        "scheduler_llm_backend": normalize_scheduler_llm_backend(r.get("scheduler_llm_backend")),
        "scheduler_tools_mode": normalize_scheduler_tools_mode(r.get("scheduler_tools_mode")),
        "scheduler_pidea_enabled": bool(r.get("scheduler_pidea_enabled", False)),
        "scheduler_instructions": (str(r.get("scheduler_instructions") or "").strip()),
        "scheduler_jobs_worker_enabled": bool(r.get("scheduler_jobs_worker_enabled", True)),
        "scheduler_jobs_ide_pidea_enabled": bool(r.get("scheduler_jobs_ide_pidea_enabled", True)),
        "scheduler_jobs_ide_pidea_timeout_sec": _bound_float(
            r.get("scheduler_jobs_ide_pidea_timeout_sec"), 300.0, 30.0, 900.0
        ),
        "workspace_allow_self_editing": bool(r.get("workspace_allow_self_editing", False)),
        "workspace_index_on_write_default": str(r.get("workspace_index_on_write_default") or "debounced"),
        "workspace_reindex_after_git_pull": bool(r.get("workspace_reindex_after_git_pull", False)),
        "workspace_nightly_reindex_enabled": bool(r.get("workspace_nightly_reindex_enabled", False)),
        "workspace_index_on_attach_enabled": bool(r.get("workspace_index_on_attach_enabled", False)),
        **media_settings_public_fields(),
        **voice_settings_public_fields(),
    }


