"""Dynamic tool forward plan: agent pins, ranking cap, context budget, catalog-first schemas."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from apps.backend.domain.agent_tools import (
    _partition_tool_specs_by_name,
    _pinned_tools_for_agent,
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


def compute_tool_forward_limits(
    *,
    context_window_tokens: int,
) -> tuple[int, int]:
    """
    Return (token_budget_estimate, max_tool_count).

    Both values are ``ratio × provider context_window`` (see ``completion_quotas_from_window``).
    When the window is unknown (0), returns ``(0, 0)`` so callers skip ranked tool forward.
    """
    window = max(0, int(context_window_tokens or 0))
    if window <= 0:
        return 0, 0

    from apps.backend.infrastructure.context_budget import completion_quotas_from_window

    quotas = completion_quotas_from_window(window, source="tool_forward_inline")
    return quotas.tools_budget_tokens, quotas.max_tool_count


def _estimate_tool_spec_tokens(spec: Any) -> int:
    try:
        payload = json.dumps(spec, ensure_ascii=False, default=str)
    except TypeError:
        payload = str(spec)
    fn = spec.get("function") if isinstance(spec, dict) else {}
    if isinstance(fn, dict):
        chars = min(len(payload), 400 + len(str(fn.get("name") or "")) + len(str(fn.get("description") or "")))
    else:
        chars = len(payload)
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


def _cap_ranked_pool(
    ranked: list[Any],
    *,
    max_slots: int,
    token_budget: int,
) -> list[Any]:
    if max_slots <= 0:
        return []
    out: list[Any] = []
    used_tokens = 0
    for spec in ranked:
        if len(out) >= max_slots:
            break
        est = _estimate_tool_spec_tokens(spec)
        if out and used_tokens + est > token_budget:
            continue
        out.append(spec)
        used_tokens += est
    return out


def _ordered_pinned_specs(specs: list[Any], pin_names: list[str]) -> list[Any]:
    pin_set = frozenset(pin_names)
    pinned_by_name = {_tool_spec_name(s): s for s in specs if _tool_spec_name(s) in pin_set}
    return [pinned_by_name[n] for n in pin_names if n in pinned_by_name]


def build_tool_forward_plan(ctx: ToolForwardContext) -> ToolForwardPlan:
    specs = list(ctx.tool_specs or [])

    token_budget, max_count = compute_tool_forward_limits(
        context_window_tokens=ctx.context_window_tokens,
    )

    spec_name_set = {_tool_spec_name(s) for s in specs if _tool_spec_name(s)}
    if ctx.agent_id:
        from apps.backend.domain.agent_registry import get_agent_registry

        ag = get_agent_registry().get_agent(ctx.agent_id) or {}
        yaml_pins = [str(x).strip() for x in (ag.get("pinned_tools") or []) if str(x).strip()]
        pin_names = [n for n in yaml_pins if n in spec_name_set]
    else:
        pin_names = [
            n for n in (_pinned_tools_for_agent(ctx.agent_id) or frozenset()) if n in spec_name_set
        ]

    pin_set = frozenset(pin_names)
    pinned_specs = _ordered_pinned_specs(specs, pin_names)
    _, rest_specs = _partition_tool_specs_by_name(specs, pin_set)

    pin_tokens = sum(_estimate_tool_spec_tokens(s) for s in pinned_specs)
    remaining_slots = max(0, max_count - len(pinned_specs))
    remaining_budget = max(0, token_budget - pin_tokens)

    ranking_applied = False
    ranked_rest = rest_specs
    if ctx.ranking_enabled and rest_specs and (ctx.user_text or "").strip():
        names = [_tool_spec_name(s) for s in rest_specs if _tool_spec_name(s)]
        triggers = build_tool_triggers_map([n for n in names if n])
        try:
            ranked_rest, ranking_applied = rank_tools_for_forward(
                rest_specs,
                ctx.user_text,
                triggers,
                category_routed=ctx.category_routed,
            )
        except Exception:
            logger.warning("tool forward: ranking failed", exc_info=True)
            ranked_rest = rest_specs

    capped_rest = _cap_ranked_pool(
        ranked_rest,
        max_slots=remaining_slots,
        token_budget=remaining_budget,
    )
    forward_specs = pinned_specs + capped_rest
    forward_names = [n for s in forward_specs if (n := _tool_spec_name(s))]

    schema_modes: dict[str, SchemaMode] = {}
    used_est = 0
    for spec in forward_specs:
        n = _tool_spec_name(spec)
        if not n:
            continue
        schema_modes[n] = "catalog"
        used_est += _estimate_tool_spec_tokens(spec)

    return ToolForwardPlan(
        forward_specs=forward_specs,
        forward_names=forward_names,
        schema_mode_per_tool=schema_modes,
        budget_tokens_allocated=token_budget,
        budget_tokens_used_estimate=used_est,
        max_tool_count=max_count,
        ranking_applied=ranking_applied,
        pins_included=list(pin_names),
        meta={
            "context_window_tokens": ctx.context_window_tokens,
            "allowlist_count": len(specs),
            "rank_pool_count": len(rest_specs),
            "pinned_count": len(pin_names),
        },
    )


def apply_schema_modes_to_specs(
    specs: list[Any],
    schema_mode_per_tool: dict[str, SchemaMode],
    *,
    default_full_schema: bool,
) -> list[Any]:
    """Rebuild specs list with per-tool full vs catalog builders."""
    _ = default_full_schema
    if not schema_mode_per_tool or all(m == "catalog" for m in schema_mode_per_tool.values()):
        from apps.backend.domain.agent_prompts import _tools_for_chat_request

        return _tools_for_chat_request(specs, full_schema=False)

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
        mode = schema_mode_per_tool.get(name, "catalog")
        builder = _full_schema_tool_function if mode == "full" else _catalog_tool_function
        out.append(builder(name, fn))
    return out
