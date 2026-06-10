"""Dynamic tool forward plan: ranking cap, context budget, schema tiers (no pins)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from apps.backend.core.config import config
from apps.backend.domain.agent_registry import get_agent_registry
from apps.backend.domain.agent_tools import (
    _tool_spec_name,
    rank_tools_for_forward,
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
    category_routed: bool = False
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

    Both values are ``ratio × provider context_window`` (see ``completion_quotas_from_window``).
    When the window is unknown (0), returns ``(0, 0)`` so callers skip ranked tool forward.
    """
    _ = model_tier
    window = max(0, int(context_window_tokens or 0))
    if window <= 0:
        return 0, 0

    from apps.backend.infrastructure.context_budget import completion_quotas_from_window

    quotas = completion_quotas_from_window(window, source="tool_forward_inline")
    return quotas.tools_budget_tokens, quotas.max_tool_count


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
    full_schema_pref: bool,
    prefer_full: frozenset[str],
) -> list[Any]:
    if max_slots <= 0:
        return []
    out: list[Any] = []
    used_tokens = 0
    for spec in ranked:
        if len(out) >= max_slots:
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
    specs = list(ctx.tool_specs or [])

    token_budget, max_count = compute_tool_forward_limits(
        context_window_tokens=ctx.context_window_tokens,
        model_tier=ctx.model_tier,
    )

    ranking_applied = False
    ranked_pool = specs
    if ctx.ranking_enabled and specs and (ctx.user_text or "").strip():
        names = [_tool_spec_name(s) for s in specs if _tool_spec_name(s)]
        triggers = build_tool_triggers_map([n for n in names if n])
        try:
            ranked_pool, ranking_applied = rank_tools_for_forward(
                specs,
                ctx.user_text,
                triggers,
                category_routed=ctx.category_routed,
            )
        except Exception:
            logger.warning("tool forward: ranking failed", exc_info=True)
            ranked_pool = specs

    prefer_full = _prefer_full_schema_names(ctx.agent_id)
    forward_specs = _cap_ranked_pool(
        ranked_pool,
        max_slots=max_count,
        token_budget=token_budget,
        full_schema_pref=ctx.full_schema_preference,
        prefer_full=prefer_full,
    )
    forward_names = [n for s in forward_specs if (n := _tool_spec_name(s))]

    schema_modes: dict[str, SchemaMode] = {}
    used_est = 0
    for spec in forward_specs:
        n = _tool_spec_name(spec)
        if not n:
            continue
        if ctx.full_schema_preference:
            mode: SchemaMode = "full" if n in prefer_full else "catalog"
            if ctx.model_tier == "weak_local" and n not in prefer_full:
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
        pins_included=[],
        meta={
            "model_tier": ctx.model_tier,
            "context_window_tokens": ctx.context_window_tokens,
            "allowlist_count": len(specs),
            "rank_pool_count": len(specs),
            "pinned_count": 0,
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
