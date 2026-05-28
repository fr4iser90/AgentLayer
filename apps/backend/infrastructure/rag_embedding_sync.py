"""Align ``rag_embedding_model`` / ``rag_embedding_dim`` with the live embedding provider."""

from __future__ import annotations

import logging
from typing import Any

from apps.backend.core import config as app_config
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.embedding_client import (
    _normalized_embedding_base,
    fetch_embedding_models_list,
    probe_embedding_output_dim,
)
logger = logging.getLogger(__name__)

# Prefer ids that look like embedding models when auto-picking from GET /v1/models.
_EMBED_NAME_HINTS = ("embed", "nomic-embed", "bge", "e5", "minilm", "gte", "sentence")
_CHAT_NAME_HINTS = ("gpt-", "gpt4", "claude", "llama", "mistral", "qwen", "nemotron", "deepseek")


def rank_embedding_model_ids(model_ids: list[str]) -> list[str]:
    """Sort provider model ids: embedding-like first, obvious chat models last."""

    def score(mid: str) -> tuple[int, str]:
        low = mid.lower()
        s = 0
        if "embed" in low:
            s -= 20
        if any(h in low for h in _EMBED_NAME_HINTS):
            s -= 10
        if any(h in low for h in _CHAT_NAME_HINTS):
            s += 15
        return (s, mid)

    return sorted({m.strip() for m in model_ids if m.strip()}, key=score)


def resolve_rag_embedding_model_from_provider(
    *,
    current_model: str,
    available_models: list[str],
    env_preferred: str | None = None,
) -> tuple[str, str]:
    """
    Pick the embedding model id to use.

    Returns (chosen_model, reason). Empty chosen_model = no provider model (skip RAG ingest).
    """
    current = (current_model or "").strip()
    available = [m.strip() for m in available_models if m and str(m).strip()]
    env_id = (env_preferred or "").strip()

    if not available:
        if current:
            return current, "provider model list empty; keeping configured model"
        return "", "no provider models listed; set embedding API or choose model in Admin"

    ranked = rank_embedding_model_ids(available)

    if current and current in available:
        return current, "configured model offered by provider"

    if env_id and env_id in available:
        return env_id, "EMBEDDING_MODEL from .env is on provider list"

    chosen = ranked[0]
    if current and current not in available:
        return (
            chosen,
            f"configured model {current_model!r} not on provider; using {chosen!r} "
            f"(provider has {len(available)} models)",
        )
    return chosen, f"auto-selected {chosen!r} from provider list"


def ensure_rag_embedding_aligned(*, log_prefix: str = "rag_embedding_sync") -> dict[str, Any]:
    """
    On startup (and callable after admin changes):

    1. GET ``/v1/models`` at ``EMBEDDING_BASE_URL``
    2. Ensure ``rag_embedding_model`` exists on the provider (or pick best match)
    3. Probe vector width and sync ``rag_embedding_dim``
    """
    summary: dict[str, Any] = {
        "ok": False,
        "model_changed": False,
        "dim_changed": False,
        "embedding_model": None,
        "embedding_dim": None,
        "available_models": [],
        "note": None,
    }

    if not _normalized_embedding_base():
        summary["note"] = "embedding API base not configured"
        logger.info("%s: skipped (%s)", log_prefix, summary["note"])
        return summary

    rs = operator_settings.rag_settings()
    if not rs.get("enabled"):
        summary["note"] = "rag disabled in operator_settings"
        logger.info("%s: skipped (%s)", log_prefix, summary["note"])
        return summary

    current_model = (rs.get("embedding_model") or "").strip()
    current_dim = int(rs.get("embedding_dim") or 0)
    timeout = min(20.0, float(rs.get("embed_timeout_sec") or 20.0))

    available, list_err = fetch_embedding_models_list(timeout=timeout)
    summary["available_models"] = available
    if list_err:
        summary["models_list_error"] = list_err[:300]

    env_model = (getattr(app_config, "EMBEDDING_MODEL", None) or "").strip() or None
    chosen_model, reason = resolve_rag_embedding_model_from_provider(
        current_model=current_model,
        available_models=available,
        env_preferred=env_model,
    )
    summary["embedding_model"] = chosen_model or None
    summary["selection_reason"] = reason

    if not chosen_model:
        summary["note"] = reason
        logger.info("%s: no embedding model selected (%s)", log_prefix, reason)
        return summary

    stored_model = (rs.get("embedding_model") or "").strip()
    model_changed = chosen_model != stored_model

    try:
        probed_dim = probe_embedding_output_dim(model_id=chosen_model)
    except Exception as e:
        logger.warning(
            "%s: could not probe dim for model %r: %s",
            log_prefix,
            chosen_model,
            e,
        )
        summary["note"] = f"dim probe failed: {e!s}"[:300]
        if model_changed:
            from apps.backend.infrastructure.operator_settings import OperatorSettingsPatch

            operator_settings.apply_operator_settings_patch(
                OperatorSettingsPatch(rag_embedding_model=chosen_model)
            )
            summary["model_changed"] = True
            _invalidate_embedding_caches()
            logger.info(
                "%s: rag_embedding_model %r -> %r (%s); dim unchanged (probe failed)",
                log_prefix,
                stored_model or "(empty)",
                chosen_model,
                reason,
            )
        return summary

    dim_changed = probed_dim != current_dim
    summary["embedding_dim"] = probed_dim

    if not model_changed and not dim_changed:
        summary["ok"] = True
        summary["note"] = "model and dim already aligned with provider"
        return summary

    from apps.backend.infrastructure.operator_settings import OperatorSettingsPatch

    body: dict[str, Any] = {}
    if model_changed:
        body["rag_embedding_model"] = chosen_model
    if dim_changed:
        body["rag_embedding_dim"] = probed_dim
    operator_settings.apply_operator_settings_patch(OperatorSettingsPatch(**body))
    _invalidate_embedding_caches()

    summary["ok"] = True
    summary["model_changed"] = model_changed
    summary["dim_changed"] = dim_changed

    if model_changed and dim_changed:
        logger.info(
            "%s: rag_embedding_model %r -> %r; rag_embedding_dim %s -> %s (%s)",
            log_prefix,
            stored_model or "(empty)",
            chosen_model,
            current_dim,
            probed_dim,
            reason,
        )
    elif model_changed:
        logger.info(
            "%s: rag_embedding_model %r -> %r (dim=%s; %s)",
            log_prefix,
            stored_model or "(empty)",
            chosen_model,
            probed_dim,
            reason,
        )
    else:
        logger.info(
            "%s: rag_embedding_dim %s -> %s (model %r; re-run ingest-docs if RAG was empty)",
            log_prefix,
            current_dim,
            probed_dim,
            chosen_model,
        )
    return summary


def _invalidate_embedding_caches() -> None:
    try:
        from apps.backend.infrastructure.code_index_qdrant import invalidate_code_index_cache

        invalidate_code_index_cache()
    except Exception:
        pass
    try:
        from apps.backend.infrastructure.embedding_client import invalidate_embedding_catalog_cache

        invalidate_embedding_catalog_cache()
    except Exception:
        pass
    try:
        from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

        invalidate_model_catalog_cache()
    except Exception:
        pass


def ensure_rag_embedding_dim_aligned(*, log_prefix: str = "rag_embedding_sync") -> bool:
    """Backward-compatible wrapper: full provider + dim alignment."""
    result = ensure_rag_embedding_aligned(log_prefix=log_prefix)
    return bool(result.get("model_changed") or result.get("dim_changed"))
