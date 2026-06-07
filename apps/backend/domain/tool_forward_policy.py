"""Dynamic tool forward plan: pins, ranking cap, context budget, schema tiers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from apps.backend.core.config import config
from apps.backend.domain.agent_registry import get_agent_registry
from apps.backend.domain.agent_tools import (
    _partition_tool_specs_by_name,
    _rank_tools_by_user_input,
    _tool_spec_name,
)
from apps.backend.domain.plugin_system.registry import get_registry

logger = logging.getLogger(__name__)

SchemaMode = Literal["full", "catalog"]


@dataclass
class ToolForwardContext:
    agent_id: str | None
    model_id: str
    context_window_tokens: int
    model_tier: str
    user_text: str
    tool_specs: list[Any]
    ranking_enabled: bool
    full_schema_preference: bool
    round_index: int = 0
    prompt_tokens_so_far: int | None = None


@dataclass
class ToolForwardPlan:
    forward_specs: list[Any]
    forward_names: list[str]
    schema_mode_per_tool: dict[str, SchemaMode] = field(default_factory=dict)
    budget_tokens_allocated: int = 0
    budget_tokens_used_estimate: int = 0
    max_tool_count: int = 0
    ranking_applied: bool = False
    pins_included: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


def resolve_pin_names(agent_id: str | None) -> frozenset[str]:
    """``pinned_tools`` from agent plugin yaml, intersected with the agent allowlist."""
    aid = (agent_id or "").strip()
    if not aid:
        return frozenset()
    ag = get_agent_registry().get_agent(aid)
    if not ag:
        return frozenset()
    allowed = frozenset(str(x).strip() for x in (ag.get("tool_names") or []) if str(x).strip())
    yaml_pins = ag.get("pinned_tools")
    if not isinstance(yaml_pins, list):
        return frozenset()
    want = [str(x).strip() for x in yaml_pins if str(x).strip()]
    return frozenset(n for n in want if n in allowed)


def pinned_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    """Agent yaml pins only — no agent-id branches or core defaults."""
    return resolve_pin_names(agent_id)


def infer_model_tier(*, model_id: str, catalog_owned_by: str | None = None) -> str:
    """strong | standard | weak_local — caps tool count independent of context window."""
    mid = (model_id or "").lower()
    own = (catalog_owned_by or "").lower()
    if "ollama" in own or mid.endswith(".gguf") or "gguf" in mid or "qwen" in mid and "api" not in own:
        if any(x in own for x in ("openai", "anthropic", "openrouter", "groq")):
            return "standard"
        return "weak_local"
    if any(x in own for x in ("openai", "anthropic", "google", "gemini")):
        return "strong"
    return "standard"


def compute_tool_forward_limits(
    *,
    context_window_tokens: int,
    model_tier: str,
) -> tuple[int, int]:
    """
    Return (token_budget_estimate, max_tool_count).

    Token budget = fraction of context window (``AGENT_TOOLS_BUDGET_*``). How many tools
    actually fit is decided in ``_cap_ranked_pool`` by summing per-tool estimates against
    that budget. ``max_tool_count`` is only a safety ceiling.
    """
    _ = model_tier
    window = max(0, int(context_window_tokens or 0))
    ratio = max(0.02, min(0.25, float(config.AGENT_TOOLS_BUDGET_RATIO)))
    min_tok = max(1000, int(config.AGENT_TOOLS_BUDGET_MIN_TOKENS))
    max_tok = max(min_tok, int(config.AGENT_TOOLS_BUDGET_MAX_TOKENS))
    if window > 0:
        raw = int(window * ratio)
        token_budget = max(min_tok, min(max_tok, raw))
    else:
        token_budget = min_tok

    if window <= 0:
        abs_max = max(1, int(config.AGENT_TOOLS_COUNT_CAP_ABSOLUTE))
        return token_budget, abs_max

    abs_max = max(1, int(config.AGENT_TOOLS_COUNT_CAP_ABSOLUTE))
    return token_budget, abs_max


def _introspection_pins_for_agent(agent_id: str | None, specs: list[Any]) -> frozenset[str]:
    """Always forward meta introspection tools when the agent declares meta.inspect/discover."""
    aid = (agent_id or "").strip()
    if not aid:
        return frozenset()
    ag = get_agent_registry().get_agent(aid)
    if not ag:
        return frozenset()
    caps = {str(c).strip() for c in (ag.get("tool_capability_any") or []) if str(c).strip()}
    if "meta.inspect" not in caps and "meta.discover" not in caps:
        return frozenset()
    from apps.backend.domain.plugin_system.tool_routing import TOOL_INTROSPECTION

    allowed = {_tool_spec_name(s) for s in specs if _tool_spec_name(s)}
    return frozenset(n for n in TOOL_INTROSPECTION if n in allowed)


def _estimate_tool_spec_tokens(spec: Any, *, full_schema: bool) -> int:
    try:
        payload = json.dumps(spec, ensure_ascii=False, default=str)
    except TypeError:
        payload = str(spec)
    chars = len(payload)
    if not full_schema:
        fn = spec.get("function") if isinstance(spec, dict) else {}
        if isinstance(fn, dict):
            chars = min(chars, 400 + len(str(fn.get("name") or "")) + len(str(fn.get("description") or "")))
    return max(80, chars // 4)


def build_tool_triggers_map(tool_names: list[str]) -> dict[str, tuple[str, ...]]:
    """Per-tool trigger substrings from plugin ``TOOL_TRIGGERS`` (domain-level)."""
    reg = get_registry()
    out: dict[str, tuple[str, ...]] = {}
    for name in tool_names:
        entry = reg.meta_entry_for_tool_name(name)
        if not entry:
            continue
        dom = entry.get("domain")
        if not isinstance(dom, str) or not dom.strip():
            continue
        dom_tr = reg.domain_trigger_substrings(dom.strip().lower())
        if dom_tr:
            out[name] = dom_tr
    return out


def _prefer_full_schema_names(agent_id: str | None) -> frozenset[str]:
    aid = (agent_id or "").strip()
    if not aid:
        return frozenset()
    ag = get_agent_registry().get_agent(aid)
    if not ag:
        return frozenset()
    raw = ag.get("tool_forward_prefer_full_schema")
    if isinstance(raw, list):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return frozenset()


def _cap_ranked_pool(
    ranked: list[Any],
    *,
    max_slots: int,
    token_budget: int,
    pin_count: int,
    full_schema_pref: bool,
    prefer_full: frozenset[str],
) -> list[Any]:
    if max_slots <= 0:
        return []
    slots = max(0, max_slots - pin_count)
    if slots <= 0:
        return []
    out: list[Any] = []
    used_tokens = 0
    for spec in ranked:
        if len(out) >= slots:
            break
        n = _tool_spec_name(spec)
        mode: SchemaMode = "full" if full_schema_pref and (n in prefer_full) else "catalog"
        if full_schema_pref:
            mode = "full"
        est = _estimate_tool_spec_tokens(spec, full_schema=mode == "full")
        if out and used_tokens + est > token_budget:
            continue
        out.append(spec)
        used_tokens += est
    return out


def build_tool_forward_plan(ctx: ToolForwardContext) -> ToolForwardPlan:
    from apps.backend.domain.agent_tools import _pinned_tools_for_agent

    specs = list(ctx.tool_specs or [])
    pin_names = _pinned_tools_for_agent(ctx.agent_id) | _introspection_pins_for_agent(
        ctx.agent_id, specs
    )

    pinned_specs, pool = _partition_tool_specs_by_name(specs, pin_names)
    pin_names_found = [_tool_spec_name(s) for s in pinned_specs if _tool_spec_name(s)]

    token_budget, max_count = compute_tool_forward_limits(
        context_window_tokens=ctx.context_window_tokens,
        model_tier=ctx.model_tier,
    )

    ranking_applied = False
    ranked_pool = pool
    if ctx.ranking_enabled and pool and (ctx.user_text or "").strip():
        names = [_tool_spec_name(s) for s in pool if _tool_spec_name(s)]
        triggers = build_tool_triggers_map([n for n in names if n])
        try:
            ranked_pool = _rank_tools_by_user_input(pool, ctx.user_text, triggers)
            ranking_applied = True
        except Exception:
            logger.warning("tool forward: ranking failed", exc_info=True)
            ranked_pool = pool

    prefer_full = _prefer_full_schema_names(ctx.agent_id)
    capped = _cap_ranked_pool(
        ranked_pool,
        max_slots=max_count,
        token_budget=token_budget,
        pin_count=len(pinned_specs),
        full_schema_pref=ctx.full_schema_preference,
        prefer_full=prefer_full,
    )

    forward_specs = pinned_specs + capped
    forward_names = [n for s in forward_specs if (n := _tool_spec_name(s))]

    schema_modes: dict[str, SchemaMode] = {}
    used_est = 0
    for spec in forward_specs:
        n = _tool_spec_name(spec)
        if not n:
            continue
        if ctx.full_schema_preference:
            mode: SchemaMode = "full" if (n in prefer_full or n in pin_names_found) else "catalog"
            if ctx.model_tier == "weak_local" and n not in pin_names_found and n not in prefer_full:
                mode = "catalog"
        else:
            mode = "catalog"
        schema_modes[n] = mode
        used_est += _estimate_tool_spec_tokens(spec, full_schema=mode == "full")

    return ToolForwardPlan(
        forward_specs=forward_specs,
        forward_names=forward_names,
        schema_mode_per_tool=schema_modes,
        budget_tokens_allocated=token_budget,
        budget_tokens_used_estimate=used_est,
        max_tool_count=max_count,
        ranking_applied=ranking_applied,
        pins_included=pin_names_found,
        meta={
            "model_tier": ctx.model_tier,
            "context_window_tokens": ctx.context_window_tokens,
            "allowlist_count": len(specs),
            "rank_pool_count": len(pool),
            "pinned_count": len(pinned_specs),
        },
    )


def apply_schema_modes_to_specs(
    specs: list[Any],
    schema_mode_per_tool: dict[str, SchemaMode],
    *,
    default_full_schema: bool,
) -> list[Any]:
    """Rebuild specs list with per-tool full vs catalog builders."""
    if not schema_mode_per_tool or default_full_schema and all(
        m == "full" for m in schema_mode_per_tool.values()
    ):
        from apps.backend.domain.agent_prompts import _tools_for_chat_request

        return _tools_for_chat_request(specs, full_schema=default_full_schema)

    from apps.backend.domain.agent_prompts import _catalog_tool_function, _full_schema_tool_function

    out: list[Any] = []
    for spec in specs:
        if not isinstance(spec, dict):
            out.append(spec)
            continue
        fn = spec.get("function")
        if not isinstance(fn, dict):
            out.append(spec)
            continue
        name = str(fn.get("name") or "").strip()
        mode = schema_mode_per_tool.get(name, "full" if default_full_schema else "catalog")
        builder = _full_schema_tool_function if mode == "full" else _catalog_tool_function
        out.append(builder(name, fn))
    return out
