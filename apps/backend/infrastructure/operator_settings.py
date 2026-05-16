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

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from apps.backend.core import config as app_config
from apps.backend.core.config import config
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_RAG_EMBEDDING_MODEL_DEFAULT = "nomic-embed-text"


def _normalize_rag_embedding_model(raw: Any) -> str:
    return (str(raw or "").strip() or _RAG_EMBEDDING_MODEL_DEFAULT)[:256]


def _rag_embedding_model_from_row(r: dict[str, Any]) -> str:
    v = r.get("rag_embedding_model")
    if v is None:
        v = r.get("rag_ollama_model")
    return _normalize_rag_embedding_model(v)


_CACHE: tuple[float, dict[str, Any]] | None = None
_TTL_SEC = 2.0


def _invalidate() -> None:
    global _CACHE
    _CACHE = None
    try:
        from apps.backend.infrastructure.embedding_client import clear_embedding_health_cache

        clear_embedding_health_cache()
    except Exception:
        pass


def invalidate_operator_settings_cache() -> None:
    """Call after external LLM endpoint sync (and similar) so cached operator row refreshes."""
    _invalidate()


def normalize_scheduler_llm_backend(raw: Any) -> str:
    s = (str(raw or "inherit")).strip().lower()
    return s if s in ("inherit", "ollama", "external") else "inherit"


def normalize_scheduler_tools_mode(raw: Any) -> str:
    s = (str(raw or "none")).strip().lower()
    return s if s in ("none", "allowlist", "full") else "none"


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
        "telegram_application_id": None,
        "telegram_bot_enabled": False,
        "telegram_bot_token": None,
        "telegram_bot_agent_bearer": None,
        "telegram_trigger_prefix": "!agent ",
        "telegram_chat_model": None,
        "dashboard_upload_max_file_mb": None,
        "dashboard_upload_allowed_mime": None,
        "llm_primary_backend": "ollama",
        "llm_smart_routing_enabled": False,
        "llm_router_ollama_model": "nemotron-3-nano:4b",
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
        "rag_embedding_model": "nomic-embed-text",
        "rag_embedding_dim": 768,
        "rag_chunk_size": 1200,
        "rag_chunk_overlap": 200,
        "rag_top_k": 8,
        "rag_embed_timeout_sec": 120.0,
        "rag_tenant_shared_domains": "agentlayer_docs",
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
                           llm_smart_routing_enabled, llm_router_ollama_model,
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
                           workspace_allow_self_editing
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
        "llm_primary_backend": (str(row[17]).strip().lower() if row[17] is not None else "") or "ollama",
        "llm_smart_routing_enabled": bool(row[18]) if row[18] is not None else False,
        "llm_router_ollama_model": (str(row[19]).strip() if row[19] is not None else "") or "nemotron-3-nano:4b",
        "llm_router_local_confidence_min": float(row[20]) if row[20] is not None else 0.7,
        "llm_router_timeout_sec": float(row[21]) if row[21] is not None else 12.0,
        "llm_route_long_prompt_chars": int(row[22]) if row[22] is not None else 8000,
        "llm_route_short_local_max_chars": int(row[23]) if row[23] is not None else 220,
        "llm_route_many_code_fences": int(row[24]) if row[24] is not None else 3,
        "llm_route_many_messages": int(row[25]) if row[25] is not None else 14,
        "memory_graph_enabled": bool(row[26]) if row[26] is not None else True,
        "memory_graph_max_hops": int(row[27]) if row[27] is not None else 2,
        "memory_graph_min_score": float(row[28]) if row[28] is not None else 0.03,
        "memory_graph_max_bullets": int(row[29]) if row[29] is not None else 14,
        "memory_graph_max_prompt_chars": int(row[30]) if row[30] is not None else 3500,
        "memory_graph_log_activations": bool(row[31]) if row[31] is not None else False,
        "memory_enabled": bool(row[32]) if row[32] is not None else True,
        "rag_enabled": bool(row[33]) if row[33] is not None else True,
        "rag_embedding_model": _normalize_rag_embedding_model(row[34]),
        "rag_embedding_dim": int(row[35]) if row[35] is not None else 768,
        "rag_chunk_size": int(row[36]) if row[36] is not None else 1200,
        "rag_chunk_overlap": int(row[37]) if row[37] is not None else 200,
        "rag_top_k": int(row[38]) if row[38] is not None else 8,
        "rag_embed_timeout_sec": float(row[39]) if row[39] is not None else 120.0,
        "rag_tenant_shared_domains": (
            str(row[40]) if row[40] is not None else "agentlayer_docs"
        ),
        "docs_root": row[41],
        "pidea_enabled": bool(row[42]) if row[42] is not None else False,
        "pidea_cdp_http_url": row[43],
        "pidea_selector_ide": row[44],
        "pidea_selector_version": row[45],
        "expose_internal_errors": bool(row[46]) if row[46] is not None else False,
        "http_client_log_level": _normalize_http_client_log_level_str(row[47]) if len(row) > 47 else "WARNING",
        "scheduler_enabled": bool(row[48]) if len(row) > 48 and row[48] is not None else False,
        "scheduler_interval_minutes": int(row[49]) if len(row) > 49 and row[49] is not None else 60,
        "scheduler_user_id": row[50] if len(row) > 50 else None,
        "scheduler_model": row[51] if len(row) > 51 else None,
        "scheduler_max_tool_rounds": int(row[52]) if len(row) > 52 and row[52] is not None else None,
        "scheduler_notify_only_if_not_ok": bool(row[53]) if len(row) > 53 and row[53] is not None else True,
        "scheduler_max_outbound_per_day": int(row[54]) if len(row) > 54 and row[54] is not None else 10,
        "scheduler_allowed_tool_packages": row[55] if len(row) > 55 else None,
        "scheduler_llm_backend": normalize_scheduler_llm_backend(row[56] if len(row) > 56 else None),
        "scheduler_tools_mode": normalize_scheduler_tools_mode(row[57] if len(row) > 57 else None),
        "scheduler_pidea_enabled": bool(row[58]) if len(row) > 58 and row[58] is not None else False,
        "scheduler_instructions": row[59] if len(row) > 59 else None,
        "scheduler_jobs_worker_enabled": bool(row[60]) if len(row) > 60 and row[60] is not None else True,
        "scheduler_jobs_ide_pidea_enabled": bool(row[61]) if len(row) > 61 and row[61] is not None else True,
        "scheduler_jobs_ide_pidea_timeout_sec": float(row[62])
        if len(row) > 62 and row[62] is not None
        else 300.0,
        "workspace_allow_self_editing": bool(row[63]) if len(row) > 63 and row[63] is not None else False,
    }


def _cached_row() -> dict[str, Any]:
    global _CACHE
    now = time.monotonic()
    if _CACHE is not None and (now - _CACHE[0]) < _TTL_SEC:
        return dict(_CACHE[1])
    row = _fetch_row()
    _CACHE = (now, row)
    return dict(row)


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


def resolved_primary_llm_backend() -> Literal["ollama", "external"]:
    r = _cached_row()
    v = (r.get("llm_primary_backend") or "ollama").strip().lower()
    return "external" if v == "external" else "ollama"


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
        "router_model": (str(r.get("llm_router_ollama_model") or "").strip() or "nemotron-3-nano:4b"),
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


def rag_settings() -> dict[str, Any]:
    """RAG chunking, embed model, top_k (operator_settings / Admin → Interfaces)."""
    r = _cached_row()
    return {
        "enabled": bool(r.get("rag_enabled", True)),
        "embedding_model": _rag_embedding_model_from_row(r),
        "embedding_dim": _bound_int(r.get("rag_embedding_dim"), 768, 32, 4096),
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


def _strip_opt(s: Any) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t or None


def normalize_external_llm_base_url(raw: str | None) -> str:
    """
    Clean operator-stored URL: trim quotes and accidental path suffixes so we do not
    build ``…/v1/chat/completions/v1/chat/completions``.

    Does **not** validate host; see :func:`external_chat_completions_url` for path rules.
    """
    if not raw:
        return ""
    s = str(raw).strip().strip("'\"")
    s = s.rstrip("/")
    low = s.lower()
    for suf in (
        "/v1/chat/completions",
        "/chat/completions",
        "/v1/models",
        "/models",
    ):
        if low.endswith(suf):
            s = s[: -len(suf)].rstrip("/")
            low = s.lower()
    # ``https://host/v1`` + ``/v1/models`` → avoid ``…/v1/v1/models``
    if low.endswith("/v1"):
        s = s[:-3].rstrip("/")
    return s


def external_api_headers(base_url: str, api_key: str) -> dict[str, str]:
    h: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if "generativelanguage.googleapis.com" in base_url.lower():
        h["x-goog-api-key"] = api_key
    return h


def external_chat_completions_url(base_url: str) -> str:
    """
    ``POST`` target for OpenAI-compatible chat completions: ``{base}/v1/chat/completions``.

    Works for OpenAI (base ``https://api.openai.com``) and Gemini OpenAI-compat (base
    ``https://generativelanguage.googleapis.com/v1beta/openai`` →
    ``…/v1beta/openai/v1/chat/completions``). A missing ``v1`` segment under the OpenAI-compat base
    (``…/openai/chat/completions``) returns **404** from Google.
    """
    bu = normalize_external_llm_base_url(base_url) or base_url.rstrip("/")
    return f"{bu.rstrip('/')}/v1/chat/completions"


def external_models_list_url(base_url: str) -> str:
    """``GET`` for OpenAI-style model list (admin); Gemini OpenAI-compat uses ``…/openai/v1/models``."""
    bu = (normalize_external_llm_base_url(base_url) or base_url).rstrip("/")
    return f"{bu}/v1/models"


def resolve_external_llm_credentials_for_catalog(
    base_url_override: str | None,
    api_key_override: str | None,
    endpoint_id: int | None = None,
) -> tuple[str, str]:
    """Host prefix and API key for admin model list (``GET …/v1/models``)."""
    if base_url_override is not None and str(base_url_override).strip():
        bu = normalize_external_llm_base_url(str(base_url_override).strip())
        key = (
            str(api_key_override).strip()
            if api_key_override is not None and str(api_key_override).strip()
            else ""
        )
        if not bu:
            raise ValueError("missing_base_url")
        if not key:
            raise ValueError("missing_api_key")
        return bu, key

    if endpoint_id is not None:
        row = db.external_llm_endpoint_by_id(int(endpoint_id))
        if not row:
            raise ValueError("unknown_endpoint")
        bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url")))
        key = _strip_opt(row.get("api_key")) or ""
        if not bu or not key:
            raise ValueError("missing_api_key")
        return bu, key

    rows = db.external_llm_endpoints_list_all()
    if rows:
        row0 = rows[0]
        bu = normalize_external_llm_base_url(_strip_opt(row0.get("base_url")))
        key = _strip_opt(row0.get("api_key")) or ""
        if bu and key:
            return bu, key

    raise ValueError("no_external_endpoint")


def _external_model_for_endpoint_row(
    row: dict[str, Any],
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> str | None:
    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"

    def col(name: str) -> str | None:
        return _strip_opt(row.get(name))

    d = col("model_default")
    if pk == "vlm":
        prof = col("model_vlm") or d
    elif pk == "agent":
        prof = col("model_agent") or d
    elif pk == "coding":
        prof = col("model_coding") or d
    else:
        prof = d

    if is_override:
        raw = _strip_opt(model_from_resolution)
        if raw and ":" in raw:
            logger.info(
                "llm: external endpoint but model override looks like an Ollama id (%r); using profile model",
                raw,
            )
            return prof
        return raw
    return prof


def external_llm_should_failover(http_status: int) -> bool:
    """Try next external endpoint on these status codes (quota, auth, overload)."""
    return http_status in (401, 403, 408, 429, 500, 502, 503, 504)


def normalize_model_catalog_owned_by(raw: Any) -> str | None:
    """Opaque catalog provider id from GET ``/v1/models`` row ``owned_by`` (see ``model_catalog_providers``)."""
    from apps.backend.infrastructure.model_catalog_providers import normalize_catalog_provider_id

    return normalize_catalog_provider_id(raw)


def _external_llm_chat_attempts(
    profile_key: str,
    is_override: bool,
    model_from_resolution: str,
) -> list[tuple[str, dict[str, str], str]]:
    pk = (profile_key or "default").strip().lower()
    if pk not in ("default", "vlm", "agent", "coding"):
        pk = "default"
    attempts: list[tuple[str, dict[str, str], str]] = []
    for row in db.external_llm_endpoints_list_all():
        bu = normalize_external_llm_base_url(_strip_opt(row.get("base_url")))
        key = _strip_opt(row.get("api_key")) or ""
        ext_model = _external_model_for_endpoint_row(row, pk, is_override, model_from_resolution)
        if not bu or not key or not ext_model:
            continue
        chat_url = external_chat_completions_url(bu)
        headers = external_api_headers(bu, key)
        attempts.append((chat_url, headers, ext_model))
    return attempts


def llm_chat_transport(
    model_from_resolution: str,
    profile_key: str,
    is_override: bool,
    *,
    backend_override: Literal["ollama", "external"] | None = None,
    catalog_owned_by: str | None = None,
) -> tuple[
    list[tuple[str, dict[str, str], str]],
    Literal["ollama", "external", "llama_cpp"],
]:
    if catalog_owned_by is None:
        raise ValueError(
            f"Could not determine which LLM provider serves model {model_from_resolution!r}. "
            "Re-select the model in the UI (provider + model) so agent_model_catalog_owned_by is sent."
        )

    from apps.backend.infrastructure.model_catalog_providers import route_chat_by_catalog_provider

    return route_chat_by_catalog_provider(
        catalog_owned_by,
        model_from_resolution,
        profile_key,
        is_override,
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
#     from apps.backend.integrations.pidea.types import ConnectionConfig

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
        "telegram_application_id": r.get("telegram_application_id") or "",
        "telegram_bot_enabled": bool(r.get("telegram_bot_enabled")),
        "telegram_bot_token_configured": bool(ttok),
        "telegram_trigger_prefix": _telegram_trigger_prefix_public(r),
        "telegram_chat_model": (str(r.get("telegram_chat_model") or "").strip())[:256],
        "dashboard_upload_max_file_mb": r.get("dashboard_upload_max_file_mb"),
        "dashboard_upload_allowed_mime": (r.get("dashboard_upload_allowed_mime") or "").strip(),
        "dashboard_upload_effective_max_bytes": effective_dashboard_upload_max_bytes(),
        "dashboard_upload_effective_allowed_mime": sorted(effective_dashboard_upload_mime()),
        "llm_primary_backend": resolved_primary_llm_backend(),
        "llm_smart_routing_enabled": bool(r.get("llm_smart_routing_enabled")),
        "llm_router_ollama_model": (str(r.get("llm_router_ollama_model") or "").strip())[:128],
        "llm_router_local_confidence_min": _bound_float(r.get("llm_router_local_confidence_min"), 0.7, 0.0, 1.0),
        "llm_router_timeout_sec": _bound_float(r.get("llm_router_timeout_sec"), 12.0, 1.0, 120.0),
        "llm_route_long_prompt_chars": _bound_int(r.get("llm_route_long_prompt_chars"), 8000, 100, 500_000),
        "llm_route_short_local_max_chars": _bound_int(r.get("llm_route_short_local_max_chars"), 220, 1, 50_000),
        "llm_route_many_code_fences": _bound_int(r.get("llm_route_many_code_fences"), 3, 1, 100),
        "llm_route_many_messages": _bound_int(r.get("llm_route_many_messages"), 14, 1, 500),
        "memory_graph_enabled": bool(r.get("memory_graph_enabled", True)),
        "memory_graph_max_hops": _bound_int(r.get("memory_graph_max_hops"), 2, 0, 4),
        "memory_graph_min_score": _bound_float(r.get("memory_graph_min_score"), 0.03, 0.0, 1.0),
        "memory_graph_max_bullets": _bound_int(r.get("memory_graph_max_bullets"), 14, 1, 50),
        "memory_graph_max_prompt_chars": _bound_int(r.get("memory_graph_max_prompt_chars"), 3500, 200, 50_000),
        "memory_graph_log_activations": bool(r.get("memory_graph_log_activations", False)),
        "memory_enabled": bool(r.get("memory_enabled", True)),
        "rag_enabled": bool(r.get("rag_enabled", True)),
        "rag_embedding_model": _rag_embedding_model_from_row(r),
        "rag_embedding_dim": _bound_int(r.get("rag_embedding_dim"), 768, 32, 4096),
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
    }


class OperatorSettingsPayload(BaseModel):
    """Full replace on PUT (empty strings clear optional fields where applicable)."""

    discord_application_id: str = Field(default="", max_length=128)
    integration_notes: str = Field(default="", max_length=8000)


class OperatorSettingsPatch(BaseModel):
    """Partial update (PATCH). Omitted fields are left unchanged; JSON null clears secrets."""

    model_config = ConfigDict(extra="forbid")

    discord_application_id: str | None = Field(default=None, max_length=128)
    integration_notes: str | None = Field(default=None, max_length=8000)
    discord_bot_enabled: bool | None = None
    discord_bot_token: str | None = Field(default=None, max_length=256)
    discord_trigger_prefix: str | None = Field(default=None, max_length=64)
    discord_chat_model: str | None = Field(default=None, max_length=256)
    telegram_bot_enabled: bool | None = None
    telegram_bot_token: str | None = Field(default=None, max_length=256)
    telegram_trigger_prefix: str | None = Field(default=None, max_length=64)
    telegram_chat_model: str | None = Field(default=None, max_length=256)
    dashboard_upload_max_file_mb: int | None = None
    dashboard_upload_allowed_mime: str | None = Field(default=None, max_length=2000)
    llm_primary_backend: str | None = Field(default=None, max_length=32)
    llm_smart_routing_enabled: bool | None = None
    llm_router_ollama_model: str | None = Field(default=None, max_length=128)
    llm_router_local_confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    llm_router_timeout_sec: float | None = Field(default=None, ge=1.0, le=120.0)
    llm_route_long_prompt_chars: int | None = Field(default=None, ge=100, le=500000)
    llm_route_short_local_max_chars: int | None = Field(default=None, ge=1, le=50000)
    llm_route_many_code_fences: int | None = Field(default=None, ge=1, le=100)
    llm_route_many_messages: int | None = Field(default=None, ge=1, le=500)
    memory_graph_enabled: bool | None = None
    memory_graph_max_hops: int | None = Field(default=None, ge=0, le=4)
    memory_graph_min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    memory_graph_max_bullets: int | None = Field(default=None, ge=1, le=50)
    memory_graph_max_prompt_chars: int | None = Field(default=None, ge=200, le=50000)
    memory_graph_log_activations: bool | None = None
    memory_enabled: bool | None = None
    rag_enabled: bool | None = None
    rag_embedding_model: str | None = Field(
        default=None,
        max_length=256,
        validation_alias=AliasChoices("rag_embedding_model", "rag_ollama_model"),
    )
    rag_embedding_dim: int | None = Field(default=None, ge=32, le=4096)
    rag_chunk_size: int | None = Field(default=None, ge=200, le=8000)
    rag_chunk_overlap: int | None = Field(default=None, ge=0, le=2000)
    rag_top_k: int | None = Field(default=None, ge=1, le=50)
    rag_embed_timeout_sec: float | None = Field(default=None, ge=5.0, le=600.0)
    rag_tenant_shared_domains: str | None = Field(default=None, max_length=4000)
    docs_root: str | None = Field(default=None, max_length=4096)
    pidea_enabled: bool | None = None
    pidea_cdp_http_url: str | None = Field(default=None, max_length=512)
    pidea_selector_ide: str | None = Field(default=None, max_length=32)
    pidea_selector_version: str | None = Field(default=None, max_length=64)
    expose_internal_errors: bool | None = None
    http_client_log_level: str | None = Field(default=None, max_length=16)
    scheduler_enabled: bool | None = None
    scheduler_interval_minutes: int | None = Field(default=None, ge=5, le=24 * 60)
    scheduler_user_id: str | None = Field(default=None, max_length=64)
    scheduler_model: str | None = Field(default=None, max_length=256)
    scheduler_max_tool_rounds: int | None = Field(default=None, ge=1, le=64)
    scheduler_notify_only_if_not_ok: bool | None = None
    scheduler_max_outbound_per_day: int | None = Field(default=None, ge=0, le=100_000)
    scheduler_allowed_tool_packages: str | None = Field(default=None, max_length=4000)
    scheduler_llm_backend: str | None = Field(default=None, max_length=16)
    scheduler_tools_mode: str | None = Field(default=None, max_length=16)
    scheduler_pidea_enabled: bool | None = None
    scheduler_instructions: str | None = Field(default=None, max_length=32000)
    scheduler_jobs_worker_enabled: bool | None = None
    scheduler_jobs_ide_pidea_enabled: bool | None = None
    scheduler_jobs_ide_pidea_timeout_sec: float | None = Field(default=None, ge=30.0, le=900.0)
    workspace_allow_self_editing: bool | None = None


def scheduler_jobs_worker_settings() -> tuple[bool, float]:
    """Persisted ``scheduler_jobs`` + ``project_runs`` worker: enabled, run timeout hint (30–900 s)."""
    r = fetch_operator_settings_row()
    w = bool(r.get("scheduler_jobs_worker_enabled", True))
    t = _bound_float(r.get("scheduler_jobs_ide_pidea_timeout_sec"), 300.0, 30.0, 900.0)
    return w, t


def interface_hints_public() -> dict[str, Any]:
    r = _fetch_row()
    am = r.get("agent_mode")
    am_s = am.strip().lower() if isinstance(am, str) else ""
    return {
        "discord_application_id": r.get("discord_application_id") or "",
        "telegram_application_id": r.get("telegram_application_id") or "",
        "agent_mode": am_s if am_s in ("sandbox", "host") else "",
        "agent_mode_effective": resolved_agent_mode(),
        "agent_mode_env": getattr(config, "AGENT_MODE", "sandbox"),
    }


class InterfaceHintsPayload(BaseModel):
    """Discord / Telegram application hints + agent execution class."""

    discord_application_id: str = Field(default="", max_length=128)
    telegram_application_id: str = Field(default="", max_length=128)
    agent_mode: str = Field(default="", max_length=16)


def apply_interface_hints(body: InterfaceHintsPayload) -> None:
    disc_v = body.discord_application_id.strip() or None
    tg_v = body.telegram_application_id.strip() or None
    raw_mode = body.agent_mode.strip().lower()
    mode_v: str | None = raw_mode if raw_mode in ("sandbox", "host") else None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operator_settings SET
                  optional_connection_key = NULL,
                  discord_application_id = %s,
                  telegram_application_id = %s,
                  agent_mode = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (disc_v, tg_v, mode_v),
            )
        conn.commit()
    _invalidate()


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
    if "llm_primary_backend" in patch:
        v = patch["llm_primary_backend"]
        if v is None:
            r["llm_primary_backend"] = "ollama"
        else:
            s = str(v).strip().lower()
            r["llm_primary_backend"] = "external" if s == "external" else "ollama"
    if "llm_smart_routing_enabled" in patch:
        r["llm_smart_routing_enabled"] = bool(patch["llm_smart_routing_enabled"])
    if "llm_router_ollama_model" in patch:
        v = patch["llm_router_ollama_model"]
        r["llm_router_ollama_model"] = (
            (str(v).strip()[:128] or "nemotron-3-nano:4b") if v is not None else "nemotron-3-nano:4b"
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
    if "rag_embedding_model" in patch:
        r["rag_embedding_model"] = _normalize_rag_embedding_model(patch["rag_embedding_model"])
    if "rag_embedding_dim" in patch:
        v = patch["rag_embedding_dim"]
        r["rag_embedding_dim"] = _bound_int(v, 768, 32, 4096) if v is not None else 768
    elif "rag_embedding_model" in patch:
        try:
            from apps.backend.infrastructure.embedding_client import probe_embedding_output_dim

            probed = probe_embedding_output_dim(model_id=r["rag_embedding_model"])
            r["rag_embedding_dim"] = _bound_int(probed, 768, 32, 4096)
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
                  llm_router_ollama_model = %s,
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
                    r.get("llm_primary_backend") or "ollama",
                    bool(r.get("llm_smart_routing_enabled")),
                    (str(r.get("llm_router_ollama_model") or "").strip() or "nemotron-3-nano:4b")[:128],
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
                    _bound_int(r.get("rag_embedding_dim"), 768, 32, 4096),
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
                ),
            )
        conn.commit()
    _invalidate()
    try:
        from apps.backend.infrastructure.embedding_client import invalidate_embedding_catalog_cache

        invalidate_embedding_catalog_cache()
    except Exception:
        pass
    if "rag_embedding_dim" in patch or "rag_embedding_model" in patch:
        try:
            from apps.backend.infrastructure.code_index_qdrant import invalidate_code_index_cache

            invalidate_code_index_cache()
        except Exception:
            pass
    try:
        from apps.backend.infrastructure.log_redaction import apply_http_client_log_levels

        apply_http_client_log_levels()
    except Exception:
        logger.debug("apply_http_client_log_levels after operator_settings patch failed", exc_info=True)


def apply_update(body: OperatorSettingsPayload) -> None:
    disc_v = body.discord_application_id.strip() or None
    notes_v = body.integration_notes.strip() or None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO operator_settings (id, discord_application_id, integration_notes, updated_at)
                VALUES (1, %s, %s, now())
                ON CONFLICT (id) DO UPDATE SET
                  discord_application_id = EXCLUDED.discord_application_id,
                  integration_notes = EXCLUDED.integration_notes,
                  updated_at = now()
                """,
                (disc_v, notes_v),
            )
        conn.commit()
    _invalidate()
