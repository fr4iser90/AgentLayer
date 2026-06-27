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

from apps.backend.infrastructure.platform import config as app_config
from apps.backend.domain.agent_runtime.config_registry import knob_by_id
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.agent_runtime import agent_config_store
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
        from apps.backend.domain.shared.identity import get_harness_profile

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
    from apps.backend.infrastructure.agent_runtime.agent_config_model_resolve import match_model_override

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
    from apps.backend.infrastructure.settings import operator_settings

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
        from apps.backend.domain.shared.identity import get_benchmark_run_id
        from apps.backend.infrastructure.benchmarks.benchmark_run_overrides import get_run_override

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


def effective_int(knob_id: str, *, tenant_id: int | None = None, default: int = 0, minimum: int = 1) -> int:
    val, _src = effective_value(knob_id, tenant_id=tenant_id)
    if val is None:
        reg = knob_by_id(knob_id) or {}
        try:
            return int(reg.get("default", default))
        except (TypeError, ValueError):
            return int(default)
    try:
        n = int(val)
    except (TypeError, ValueError):
        return int(default)
    return max(minimum, n)


def effective_float(
    knob_id: str,
    *,
    tenant_id: int | None = None,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    val, _src = effective_value(knob_id, tenant_id=tenant_id)
    if val is None:
        reg = knob_by_id(knob_id) or {}
        try:
            raw = reg.get("default", default)
            n = float(raw)
        except (TypeError, ValueError):
            n = float(default)
    else:
        try:
            n = float(val)
        except (TypeError, ValueError):
            n = float(default)
    return max(minimum, min(maximum, n))


def effective_string_list(knob_id: str, *, tenant_id: int | None = None) -> tuple[str, ...] | None:
    val, _src = effective_value(knob_id, tenant_id=tenant_id)
    if isinstance(val, list):
        items = tuple(str(x).strip() for x in val if str(x).strip())
        return items if items else None
    return None


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


def context_compaction_enabled(*, tenant_id: int | None = None) -> bool:
    return effective_bool("context.compaction_enabled", tenant_id=tenant_id, default=app_config.CHAT_CONTEXT_COMPACTION_ENABLED)


def context_agent_loop_trim_enabled(*, tenant_id: int | None = None) -> bool:
    return effective_bool(
        "context.agent_loop_trim_enabled",
        tenant_id=tenant_id,
        default=app_config.CHAT_CONTEXT_AGENT_LOOP_TRIM_ENABLED,
    )


def context_keep_recent_tool_rounds(*, tenant_id: int | None = None) -> int:
    return effective_int(
        "context.keep_recent_tool_rounds",
        tenant_id=tenant_id,
        default=app_config.CHAT_CONTEXT_KEEP_RECENT_TOOL_ROUNDS,
        minimum=2,
    )


def context_tools_budget_ratio(*, tenant_id: int | None = None) -> float:
    return effective_float(
        "context.tools_budget_ratio",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOLS_BUDGET_RATIO,
        minimum=0.01,
        maximum=0.25,
    )


def context_tool_result_max_ratio(*, tenant_id: int | None = None) -> float:
    return effective_float(
        "context.tool_result_max_ratio",
        tenant_id=tenant_id,
        default=app_config.CHAT_CONTEXT_TOOL_RESULT_MAX_RATIO,
        minimum=0.002,
        maximum=0.15,
    )


def tool_thrash_enabled(*, tenant_id: int | None = None) -> bool:
    return effective_bool("agent.tool_thrash_enabled", tenant_id=tenant_id, default=app_config.AGENT_TOOL_THRASH_ENABLED)


def tool_thrash_streak_max(*, tenant_id: int | None = None) -> int:
    return effective_int(
        "agent.tool_thrash_streak_max",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOL_THRASH_STREAK_MAX,
        minimum=2,
    )


def doom_loop_enabled(*, tenant_id: int | None = None) -> bool:
    return effective_bool("agent.doom_loop_enabled", tenant_id=tenant_id, default=app_config.AGENT_TOOL_DOOM_LOOP_ENABLED)


def doom_loop_streak_max(*, tenant_id: int | None = None) -> int:
    return effective_int(
        "agent.doom_loop_streak_max",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOL_DOOM_LOOP_STREAK_MAX,
        minimum=2,
    )


def delegate_max_artifact_refs(*, tenant_id: int | None = None) -> int:
    return effective_int("delegate.max_artifact_refs", tenant_id=tenant_id, default=8, minimum=1)


def delegate_infer_git_forensics(*, tenant_id: int | None = None) -> bool:
    return effective_bool("delegate.infer_git_forensics", tenant_id=tenant_id, default=True)


def delegate_allowed_modes(*, tenant_id: int | None = None) -> frozenset[str] | None:
    modes = effective_string_list("delegate.allowed_modes", tenant_id=tenant_id)
    return frozenset(modes) if modes else None


def delegate_mode_allowed(mode: str | None, *, tenant_id: int | None = None) -> bool:
    allowed = delegate_allowed_modes(tenant_id=tenant_id)
    if not allowed:
        return True
    norm = str(mode or "").strip().lower()
    if not norm:
        return True
    return norm in allowed


def knowledge_orchestration_enabled(*, tenant_id: int | None = None) -> bool:
    return effective_bool("knowledge.orchestration_enabled", tenant_id=tenant_id, default=False)


def knowledge_orchestration_mode(*, tenant_id: int | None = None) -> str:
    val, _src = effective_value("knowledge.orchestration_mode", tenant_id=tenant_id)
    mode = str(val or "agent_native").strip().lower()
    if mode in ("basic_rag", "agent_native"):
        return mode
    return "agent_native"


def knowledge_extractor_backend(*, tenant_id: int | None = None) -> str:
    val, _src = effective_value("knowledge.extractor_backend", tenant_id=tenant_id)
    backend = str(val or "deterministic").strip().lower()
    if backend in ("deterministic", "llm", "hybrid"):
        return backend
    return "deterministic"


def knowledge_extractor_provider_id(*, tenant_id: int | None = None) -> str | None:
    val, _src = effective_value("knowledge.extractor_provider_id", tenant_id=tenant_id)
    s = str(val or "").strip()
    return s or None


def knowledge_extractor_model(*, tenant_id: int | None = None) -> str | None:
    val, _src = effective_value("knowledge.extractor_model", tenant_id=tenant_id)
    s = str(val or "").strip()
    return s or None


_AGENT_YAML_KNOBS: dict[str, dict[str, str]] = {
    "general": {
        "agent.general.system_prompt": "system_prompt",
        "agent.general.pinned_tools": "pinned_tools",
    },
    "coding": {
        "agent.coding.system_prompt": "system_prompt",
        "agent.coding.pinned_tools": "pinned_tools",
        "agent.coding.tool_allowlist": "tool_allowlist",
        "agent.coding.tool_discipline_preset": "tool_discipline_preset",
        "agent.coding.coding_tools_permission_ask": "coding_tools_permission_ask",
    },
}


def agent_yaml_overlay(agent_id: str, *, tenant_id: int | None = None) -> dict[str, Any]:
    """DB overlay fields for agent registry entries (general, coding)."""
    field_map = _AGENT_YAML_KNOBS.get(agent_id)
    if not field_map:
        return {}
    out: dict[str, Any] = {}
    for kid, field in field_map.items():
        val, _src = effective_value(kid, tenant_id=tenant_id)
        if val is None:
            continue
        if field == "system_prompt":
            if isinstance(val, str) and val.strip():
                out[field] = val
        elif field in ("pinned_tools", "tool_allowlist"):
            if isinstance(val, list) and val:
                out[field] = [str(x).strip() for x in val if str(x).strip()]
        elif field == "tool_discipline_preset":
            if isinstance(val, str) and val.strip():
                out[field] = val.strip()
        elif field == "coding_tools_permission_ask":
            if isinstance(val, bool):
                out[field] = val
    return out


def merge_agent_definition(agent: dict[str, Any], *, tenant_id: int | None = None) -> dict[str, Any]:
    aid = str(agent.get("id") or "")
    overlay = agent_yaml_overlay(aid, tenant_id=tenant_id)
    merged = dict(agent)
    if overlay:
        merged.update(overlay)
    tid = _resolve_tenant_id(tenant_id)
    if tid is not None and aid:
        try:
            from apps.backend.infrastructure.agent_runtime import agent_prompt_version_store

            published = agent_prompt_version_store.get_published_prompt(tenant_id=tid, agent_id=aid)
        except Exception as exc:
            logger.debug("agent prompt overlay skipped for %s: %s", aid, exc)
            published = None
        if published and isinstance(published.get("prompt_text"), str) and published["prompt_text"].strip():
            merged["system_prompt"] = published["prompt_text"]
            merged["system_prompt_source"] = "db_published"
            merged["system_prompt_version"] = published.get("version")
            merged["system_prompt_version_id"] = published.get("id")
    if not overlay and merged == agent:
        return agent
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

    if knob_id == "context.compaction_enabled":
        return context_compaction_enabled(tenant_id=tenant_id), "implicit_default"

    if knob_id == "context.agent_loop_trim_enabled":
        return context_agent_loop_trim_enabled(tenant_id=tenant_id), "implicit_default"

    if knob_id == "context.keep_recent_tool_rounds":
        return context_keep_recent_tool_rounds(tenant_id=tenant_id), "implicit_default"

    if knob_id == "context.tools_budget_ratio":
        return context_tools_budget_ratio(tenant_id=tenant_id), "implicit_default"

    if knob_id == "context.tool_result_max_ratio":
        return context_tool_result_max_ratio(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.tool_thrash_enabled":
        return tool_thrash_enabled(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.tool_thrash_streak_max":
        return tool_thrash_streak_max(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.doom_loop_enabled":
        return doom_loop_enabled(tenant_id=tenant_id), "implicit_default"

    if knob_id == "agent.doom_loop_streak_max":
        return doom_loop_streak_max(tenant_id=tenant_id), "implicit_default"

    if knob_id == "delegate.max_artifact_refs":
        return delegate_max_artifact_refs(tenant_id=tenant_id), "implicit_default"

    if knob_id == "delegate.infer_git_forensics":
        return delegate_infer_git_forensics(tenant_id=tenant_id), "implicit_default"

    if knob_id == "knowledge.orchestration_enabled":
        return knowledge_orchestration_enabled(tenant_id=tenant_id), "implicit_default"

    if knob_id == "knowledge.orchestration_mode":
        return knowledge_orchestration_mode(tenant_id=tenant_id), "implicit_default"

    if knob_id == "knowledge.extractor_backend":
        return knowledge_extractor_backend(tenant_id=tenant_id), "implicit_default"

    if knob_id == "knowledge.extractor_provider_id":
        return knowledge_extractor_provider_id(tenant_id=tenant_id) or "", "implicit_default"

    if knob_id == "knowledge.extractor_model":
        return knowledge_extractor_model(tenant_id=tenant_id) or "", "implicit_default"

    if knob_id == "agent.coding.coding_tools_permission_ask":
        val, src = effective_value(knob_id, tenant_id=tenant_id, catalog_owned_by=catalog_owned_by, model=model)
        if val is not None:
            return val, src
        file_val = _file_default_value(knob_by_id(knob_id) or {})
        if isinstance(file_val, bool):
            return file_val, "file_default"
        return False, "file_default"

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
