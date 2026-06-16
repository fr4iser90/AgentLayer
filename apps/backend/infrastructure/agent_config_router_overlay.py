"""DB-backed router phrase overlays (router.delegate/catalog/task knobs)."""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.backend.domain.agent_config_registry import knob_by_id
from apps.backend.domain.identity import get_identity
from apps.backend.domain.plugin_system.router_phrases import _collect_phrases, _normalize_phrase
from apps.backend.infrastructure import agent_config_effective, agent_config_store

logger = logging.getLogger(__name__)

_ROUTER_KNOB_BY_DOMAIN: dict[str, str] = {
    "delegate": "router.delegate",
    "catalog": "router.catalog",
    "task": "router.task",
}

_DOMAIN_BY_KNOB: dict[str, str] = {v: k for k, v in _ROUTER_KNOB_BY_DOMAIN.items()}

_CACHE: dict[int, tuple[float, dict[str, frozenset[str]]]] = {}
_CACHE_TTL_SEC = 5.0


def invalidate_router_overlay_cache(tenant_id: int | None = None) -> None:
    if tenant_id is None:
        _CACHE.clear()
    else:
        _CACHE.pop(int(tenant_id), None)


def _resolve_tenant_id(tenant_id: int | None) -> int | None:
    if tenant_id is not None:
        return int(tenant_id)
    try:
        tid, _uid = get_identity()
        return int(tid) if tid is not None else None
    except Exception:
        return None


def _phrases_from_overlay(value: Any) -> frozenset[str]:
    if not isinstance(value, dict):
        return frozenset()
    phrases_node = value.get("phrases")
    if phrases_node is None:
        return frozenset()
    out: set[str] = set()
    for p in _collect_phrases(phrases_node):
        norm = _normalize_phrase(p)
        if norm:
            out.add(norm)
    return frozenset(out)


def overlay_phrases_for_domain(domain: str, *, tenant_id: int | None = None) -> frozenset[str]:
    tid = _resolve_tenant_id(tenant_id)
    if tid is None:
        return frozenset()
    now = time.monotonic()
    hit = _CACHE.get(tid)
    if hit is not None and now - hit[0] <= _CACHE_TTL_SEC:
        return hit[1].get(domain.strip().lower(), frozenset())
    merged: dict[str, frozenset[str]] = {}
    for dom, kid in _ROUTER_KNOB_BY_DOMAIN.items():
        val, _src = agent_config_effective.effective_value(kid, tenant_id=tid)
        merged[dom] = _phrases_from_overlay(val)
    _CACHE[tid] = (now, merged)
    return merged.get(domain.strip().lower(), frozenset())


def domain_for_knob(knob_id: str) -> str | None:
    return _DOMAIN_BY_KNOB.get(knob_id)


def apply_router_overlay_to_registry(*, tenant_id: int) -> None:
    """Merge tenant router overlays into live registry trigger maps."""
    from apps.backend.domain.plugin_system.registry import get_registry

    reg = get_registry()
    with reg._lock:
        triggers = dict(reg._router_cat_TOOL_TRIGGERS)
        tools = dict(reg._router_cat_tools)
        for dom, kid in _ROUTER_KNOB_BY_DOMAIN.items():
            val, src = agent_config_effective.effective_value(kid, tenant_id=tenant_id)
            if src != "db_override":
                continue
            overlay = _phrases_from_overlay(val)
            if not overlay:
                continue
            yaml_domain = dom
            if isinstance(val, dict):
                raw_dom = val.get("domain")
                if isinstance(raw_dom, str) and raw_dom.strip():
                    yaml_domain = raw_dom.strip().lower()
            existing = set(triggers.get(yaml_domain, frozenset()))
            existing.update(overlay)
            triggers[yaml_domain] = frozenset(existing)
            if yaml_domain not in tools:
                tools[yaml_domain] = frozenset()
        reg._router_cat_TOOL_TRIGGERS = triggers
        reg._router_cat_tools = tools
    invalidate_router_overlay_cache(tenant_id)
