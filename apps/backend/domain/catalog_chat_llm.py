"""Resolve chat LLM model + catalog provider from the UI catalog (no env model fallbacks)."""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.backend.infrastructure.model_catalog_routing import infer_catalog_owned_by
from apps.backend.infrastructure.model_catalog_providers import (
    get_provider_spec,
    list_provider_specs,
    resolve_model_for_provider,
)
from apps.backend.infrastructure.operator_settings import normalize_model_catalog_owned_by

logger = logging.getLogger(__name__)

_PROFILE_KEYS = frozenset({"default", "vlm", "agent", "coding"})

# ``/auth/setup-status`` and the SPA boot path call this often; avoid re-probing every provider per request.
_REACHABLE_CACHE_TTL_SEC = 30.0
_reachable_cache: dict[tuple[str, ...], tuple[float, str | None]] = {}


def invalidate_reachable_catalog_cache() -> None:
    _reachable_cache.clear()


def _normalize_profile(profile_key: str) -> str:
    pk = (profile_key or "default").strip().lower()
    return pk if pk in _PROFILE_KEYS else "default"


def pick_reachable_catalog_provider(*, prefer: tuple[str, ...] = ()) -> str | None:
    """First configured provider that is reachable and exposes at least one model."""
    from apps.backend.infrastructure.model_catalog_providers import fetch_models_for_provider

    pref_key = tuple(prefer)
    now = time.monotonic()
    cached = _reachable_cache.get(pref_key)
    if cached is not None and now - cached[0] <= _REACHABLE_CACHE_TTL_SEC:
        return cached[1]

    order: list[str] = []
    seen: set[str] = set()
    for pid in prefer:
        n = normalize_model_catalog_owned_by(pid)
        if n and n not in seen:
            order.append(n)
            seen.add(n)
    for spec in list_provider_specs():
        if spec.provider_id not in seen:
            order.append(spec.provider_id)
            seen.add(spec.provider_id)

    for pid in order:
        spec = get_provider_spec(pid)
        if spec is None or not spec.base_url.strip():
            continue
        rows, meta = fetch_models_for_provider(spec)
        if meta.get("reachable") and rows:
            _reachable_cache[pref_key] = (now, pid)
            return pid
    for pid in order:
        if get_provider_spec(pid) is not None:
            _reachable_cache[pref_key] = (now, pid)
            return pid
    _reachable_cache[pref_key] = (now, None)
    return None


def finalize_catalog_chat_llm(
    *,
    model: str,
    profile_key: str,
    is_override: bool,
    catalog_owned_by: str | None,
) -> tuple[str, str]:
    """
  Return ``(effective_model, catalog_owned_by)`` for ``chat_completion`` / ``llm_chat_transport``.

  Requires a catalog provider (UI or inferable from model id). Does not use ``OLLAMA_DEFAULT_MODEL``.
    """
    mid = (model or "").strip()
    catalog = normalize_model_catalog_owned_by(catalog_owned_by)
    if not catalog and mid and mid.lower() not in _PROFILE_KEYS:
        catalog = infer_catalog_owned_by(mid)
    if not catalog:
        raise ValueError(
            "No LLM catalog provider for this request. Pick a model in the chat UI "
            "(provider + model from GET /v1/models) or configure LLM endpoints in Admin → Interfaces."
        )

    spec = get_provider_spec(catalog)
    if spec is None:
        raise ValueError(f"Unknown catalog provider {catalog!r}. Refresh the model list in the UI.")

    pk = _normalize_profile(profile_key)
    effective = resolve_model_for_provider(spec, pk, is_override, mid)
    if not effective or effective.strip().lower() in _PROFILE_KEYS:
        raise ValueError(
            f"No model configured for provider {catalog!r} (profile={pk}). "
            "Set model_default / profile models on the LLM endpoint in Admin → Interfaces, "
            "or pick a concrete model in the chat composer."
        )

    if is_override and mid and mid.lower() not in _PROFILE_KEYS:
        effective = mid

    return effective.strip(), catalog


def catalog_llm_body_extras(
    *,
    model: str | None = None,
    catalog_owned_by: str | None = None,
    profile_key: str = "agent",
    prefer_providers: tuple[str, ...] = ("provider_1", "provider_2"),
) -> dict[str, Any]:
    """
    Build ``model`` + ``agent_model_catalog_owned_by`` for non-UI callers (scheduler, bridges).

    Uses operator-configured model when provided; otherwise endpoint profile defaults from catalog.
    """
    catalog = normalize_model_catalog_owned_by(catalog_owned_by)
    mid = (model or "").strip() or None

    if not catalog and mid:
        catalog = infer_catalog_owned_by(mid)
    if not catalog:
        catalog = pick_reachable_catalog_provider(prefer=prefer_providers)

    eff, catalog = finalize_catalog_chat_llm(
        model=mid or profile_key,
        profile_key=profile_key,
        is_override=bool(mid and mid.lower() not in _PROFILE_KEYS),
        catalog_owned_by=catalog,
    )
    return {"model": eff, "agent_model_catalog_owned_by": catalog}
