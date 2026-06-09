"""Infer catalog ``owned_by`` only when unambiguous (see :mod:`model_catalog_providers`)."""

from __future__ import annotations

import time

from apps.backend.infrastructure.model_catalog_providers import build_model_provider_index

_CACHE_TTL_SEC = 45.0
_cache_at: float = 0.0
_cache_index: dict[str, list[str]] = {}


def infer_catalog_owned_by(model_id: str) -> str | None:
    """When the client omits ``agent_model_catalog_owned_by``, use only if one provider lists this id."""
    mid = (model_id or "").strip()
    if not mid:
        return None
    global _cache_at, _cache_index
    now = time.monotonic()
    if now - _cache_at > _CACHE_TTL_SEC or not _cache_index:
        _cache_index = build_model_provider_index()
        _cache_at = now
    owners = _cache_index.get(mid, [])
    if len(owners) == 1:
        return owners[0]
    return None


def invalidate_model_catalog_cache() -> None:
    global _cache_at, _cache_index
    _cache_at = 0.0
    _cache_index = {}
    from apps.backend.domain.catalog_chat_llm import invalidate_reachable_catalog_cache

    invalidate_reachable_catalog_cache()
    from apps.backend.infrastructure.model_catalog_providers import invalidate_provider_specs_cache

    invalidate_provider_specs_cache()
    from apps.backend.infrastructure.llm_concurrency import invalidate_llm_concurrency_cache

    invalidate_llm_concurrency_cache()
