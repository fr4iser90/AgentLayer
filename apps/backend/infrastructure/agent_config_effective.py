"""Resolve effective agent tuning values: DB override → registry / file / operator DB.

Policy: runtime_config knobs are never tuned via .env. When no DB override exists,
use registry defaults or on-disk agent/router files — not process env bootstrap.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import yaml

from apps.backend.core import config as app_config
from apps.backend.domain.agent_config_registry import knob_by_id
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure import agent_config_store
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]

_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_MODEL_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SEC = 5.0


def invalidate_agent_config_cache(tenant_id: int | None = None) -> None:
    if tenant_id is None:
        _CACHE.clear()
        _MODEL_CACHE.clear()
    else:
        _CACHE.pop(int(tenant_id), None)
        _MODEL_CACHE.pop(int(tenant_id), None)


def _resolve_tenant_id(tenant_id: int | None) -> int | None:
    if tenant_id is not None:
        return int(tenant_id)
    try:
        tid, _uid = get_identity()
        return int(tid) if tid is not None else None
    except Exception:
        return None


def _cached_overrides(tenant_id: int) -> dict[str, Any]:
    now = time.monotonic()
    hit = _CACHE.get(tenant_id)
    if hit is not None and now - hit[0] <= _CACHE_TTL_SEC:
        return hit[1]
    overrides = agent_config_store.list_overrides(tenant_id)
    _CACHE[tenant_id] = (now, overrides)
    return overrides


def _cached_model_override_rows(tenant_id: int) -> list[dict[str, Any]]:
    now = time.monotonic()
    hit = _MODEL_CACHE.get(tenant_id)
    if hit is not None and now - hit[0] <= _CACHE_TTL_SEC:
        return hit[1]
    rows = agent_config_store.list_model_overrides(tenant_id)
    _MODEL_CACHE[tenant_id] = (now, rows)
    return rows


def _resolve_harness_scope(
    *,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> tuple[str, str] | None:
    if catalog_owned_by is not None or model is not None:
        catalog = str(catalog_owned_by or "").strip()
        mid = str(model or "").strip()
        return (catalog, mid) if catalog else None
    try:
        from apps.backend.domain.identity import get_harness_profile

        return get_harness_profile()
    except Exception:
        return None


def _model_override_value(
    tenant_id: int,
    knob_id: str,
    *,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> tuple[Any, str] | None:
    scope = _resolve_harness_scope(catalog_owned_by=catalog_owned_by, model=model)
    if scope is None:
        return None
    catalog, mid = scope
    from apps.backend.infrastructure.agent_config_model_resolve import match_model_override

    matched, source = match_model_override(
        _cached_model_override_rows(tenant_id),
        catalog_owned_by=catalog,
        model=mid,
    )
    if matched is None:
        return None
    knobs = matched.get("knobs_json") or {}
    if not isinstance(knobs, dict) or knob_id not in knobs:
        return None
    return knobs[knob_id], source


def _file_default_value(knob: dict[str, Any]) -> Any:
    layer = str(knob.get("layer") or "")
    path = str(knob.get("path") or "").strip()
    if not path:
        return None
    full = _REPO_ROOT / path
    if not full.is_file():
        return None
    if layer == "agent_yaml":
        if path.endswith(".md"):
            return full.read_text(encoding="utf-8")
        data = yaml.safe_load(full.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            field = str(knob.get("field") or "").strip()
            if field:
                return data.get(field)
        return None
    if layer == "router_yaml":
        data = yaml.safe_load(full.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    return None


def _registry_default_value(knob: dict[str, Any]) -> Any:
    if "default" in knob:
        return knob.get("default")
    return None


def _operator_settings_value(knob: dict[str, Any]) -> Any | None:
    key = str(knob.get("operator_settings_key") or "").strip()
    if not key:
        return None
    from apps.backend.infrastructure import operator_settings

    row = operator_settings._cached_row()
    if key in row:
        return row.get(key)
    return None


def default_value(knob_id: str) -> tuple[Any, str]:
    """Non-DB default for a knob (registry, file, or operator_settings row)."""
    knob = knob_by_id(knob_id) or {}
    layer = str(knob.get("layer") or "")

    if layer == "operator":
        val = _operator_settings_value(knob)
        if val is not None:
            return val, "operator_settings"
        reg = _registry_default_value(knob)
        return reg, "registry_default"

    if layer == "runtime_config":
        reg = _registry_default_value(knob)
        return reg, "registry_default"

    if layer in ("agent_yaml", "router_yaml"):
        file_val = _file_default_value(knob)
        if file_val is not None:
            return file_val, "file_default"
        reg = _registry_default_value(knob)
        return reg, "registry_default"

    reg = _registry_default_value(knob)
    return reg, "registry_default"


def effective_value(
    knob_id: str,
    *,
    tenant_id: int | None = None,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> tuple[Any, str]:
    """Return ``(value, source)`` — never labels env bootstrap for runtime knobs."""
    try:
        from apps.backend.domain.identity import get_benchmark_run_id
        from apps.backend.infrastructure.benchmark_run_overrides import get_run_override

        rid = get_benchmark_run_id()
        if rid is not None:
            ov = get_run_override(rid, knob_id)
            if ov is not None:
                return ov, "bench_run_override"
    except Exception:
        pass

    tid = _resolve_tenant_id(tenant_id)
    if tid is not None and db.pool_ready():
        model_hit = _model_override_value(
            tid,
            knob_id,
            catalog_owned_by=catalog_owned_by,
            model=model,
        )
        if model_hit is not None:
            return model_hit
        ov = _cached_overrides(tid).get(knob_id)
        if ov is not None:
            return ov, "db_override"
    return default_value(knob_id)


def effective_int(knob_id: str, *, tenant_id: int | None = None, default: int = 0) -> int:
    val, _src = effective_value(knob_id, tenant_id=tenant_id)
    if val is None:
        reg = knob_by_id(knob_id) or {}
        try:
            return int(reg.get("default", default))
        except (TypeError, ValueError):
            return int(default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return int(default)


def effective_bool(knob_id: str, *, tenant_id: int | None = None, default: bool = False) -> bool:
    val, _src = effective_value(knob_id, tenant_id=tenant_id)
    if val is None:
        reg = knob_by_id(knob_id) or {}
        if isinstance(reg.get("default"), bool):
            return bool(reg.get("default"))
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def effective_domain_order(*, tenant_id: int | None = None) -> tuple[str, ...]:
    val, _src = effective_value("tool_routing.domain_order", tenant_id=tenant_id)
    if isinstance(val, list):
        return tuple(str(x).strip().lower() for x in val if str(x).strip())
    if isinstance(val, str) and val.strip():
        return tuple(x.strip().lower() for x in val.split(",") if x.strip())
    return tuple(app_config.AGENT_TOOL_DOMAIN_ORDER)


def max_tool_rounds(*, tenant_id: int | None = None) -> int:
    return effective_int("agent.max_tool_rounds", tenant_id=tenant_id, default=20)


def subagent_max_tool_rounds(*, tenant_id: int | None = None) -> int:
    return effective_int("agent.subagent_max_tool_rounds", tenant_id=tenant_id, default=20)


def subagent_timeout_sec(*, tenant_id: int | None = None) -> float | None:
    val, _src = effective_value("agent.subagent_timeout_sec", tenant_id=tenant_id)
    if val is None:
        return app_config.SUBAGENT_TIMEOUT_SEC
    try:
        n = float(val)
    except (TypeError, ValueError):
        return app_config.SUBAGENT_TIMEOUT_SEC
    return n if n > 0 else None


def agent_yaml_overlay(agent_id: str, *, tenant_id: int | None = None) -> dict[str, Any]:
    """DB overlay fields for a given agent id (general only today)."""
    if agent_id != "general":
        return {}
    out: dict[str, Any] = {}
    sp, _src = effective_value("agent.general.system_prompt", tenant_id=tenant_id)
    if isinstance(sp, str) and sp.strip():
        out["system_prompt"] = sp
    pins, _src2 = effective_value("agent.general.pinned_tools", tenant_id=tenant_id)
    if isinstance(pins, list) and pins:
        out["pinned_tools"] = [str(x).strip() for x in pins if str(x).strip()]
    return out


def merge_agent_definition(agent: dict[str, Any], *, tenant_id: int | None = None) -> dict[str, Any]:
    aid = str(agent.get("id") or "")
    overlay = agent_yaml_overlay(aid, tenant_id=tenant_id)
    if not overlay:
        return agent
    merged = dict(agent)
    merged.update(overlay)
    return merged


def display_value(
    knob_id: str,
    *,
    tenant_id: int | None = None,
    catalog_owned_by: str | None = None,
    model: str | None = None,
) -> tuple[Any, str]:
    """Resolved value for admin UI, including implicit runtime defaults when unset in DB."""
    val, src = effective_value(
        knob_id,
        tenant_id=tenant_id,
        catalog_owned_by=catalog_owned_by,
        model=model,
    )
    if val is not None:
        return val, src

    if knob_id == "tool_routing.domain_order":
        order = effective_domain_order(tenant_id=tenant_id)
        if order:
            return list(order), "implicit_default"
        return None, "implicit_default"

    if knob_id == "agent.max_tool_rounds":
        return max_tool_rounds(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.subagent_max_tool_rounds":
        return subagent_max_tool_rounds(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.subagent_timeout_sec":
        return subagent_timeout_sec(tenant_id=tenant_id), "implicit_default"

    if knob_id == "tool_routing.router_strict_default":
        return effective_bool(knob_id, tenant_id=tenant_id, default=True), "implicit_default"

    knob = knob_by_id(knob_id) or {}
    if "default" in knob:
        return knob.get("default"), "registry_default"

    if str(knob.get("layer") or "") in ("agent_yaml", "router_yaml"):
        file_val = _file_default_value(knob)
        if file_val is not None:
            return file_val, "file_default"

    return val, src
