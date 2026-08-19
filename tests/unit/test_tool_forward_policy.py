"""Tests for dynamic tool forward policy (pins, ranking cap, context budget)."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.plugins import plugin_registry_service as _plugin_registry_service  # noqa: F401
from apps.backend.infrastructure.tools import tool_forward_policy_service as _tool_forward_policy_service  # noqa: F401
from apps.backend.domain.tools.forward_policy import (
    ToolForwardContext,
    apply_schema_modes_to_specs,
    build_tool_forward_plan,
    build_tool_triggers_map,
    compute_tool_forward_limits,
)


def _spec(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": {"type": "object", "properties": {"x": {"type": "string"}}},
        },
    }


def test_compute_tool_forward_limits_uses_context_budget():
    from apps.backend.infrastructure.platform import config as cfg

    cfg.config.AGENT_TOOLS_BUDGET_RATIO = 0.06
    cfg.config.AGENT_TOOLS_COUNT_CAP_RATIO = 0.0004
    tok, count = compute_tool_forward_limits(context_window_tokens=128_000)
    assert tok == int(128_000 * 0.06)
    assert count == int(128_000 * 0.0004)
    tok0, count0 = compute_tool_forward_limits(context_window_tokens=0)
    assert tok0 == 0
    assert count0 == 0


def test_build_tool_forward_plan_uses_ranking_not_pins(monkeypatch):
    specs = [_spec(n) for n in ("dashboard.read", "propose_layouts", "patch_layout", "list", "other_a", "other_b")]

    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy.rank_tools_for_forward",
        lambda tools, text, triggers, **kw: (list(reversed(tools)), True),
    )
    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy._pinned_tools_for_agent",
        lambda agent_id: frozenset(),
    )

    class _NoPinsReg:
        def get_agent(self, agent_id):
            return {"pinned_tools": []}

    monkeypatch.setattr(
        "apps.backend.domain.agent_runtime.registry.get_agent_registry",
        lambda: _NoPinsReg(),
    )

    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="dashboard",
            model_id="qwen2.5:7b",
            context_window_tokens=262_144,
            user_text="zeig mir layout varianten",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=True,
        )
    )
    assert all(m == "catalog" for m in plan.schema_mode_per_tool.values())
    assert plan.ranking_applied is True
    assert plan.forward_names[0] == "other_b"
    assert len(plan.forward_names) <= plan.max_tool_count


def test_apply_schema_modes_to_specs_catalog_vs_full():
    specs = [_spec("a"), _spec("b")]
    out = apply_schema_modes_to_specs(
        specs,
        {"a": "full", "b": "catalog"},
        default_full_schema=False,
    )
    assert len(out) == 2
    a_params = out[0]["function"]["parameters"]
    b_desc = out[1]["function"]["description"]
    assert a_params.get("properties", {}).get("x")
    assert "abbreviated" in b_desc.lower() or "catalog" in b_desc.lower()


def test_build_tool_triggers_map_from_plugin_domains():
    triggers = build_tool_triggers_map(["propose_layouts", "patch_layout"])
    pl = triggers.get("propose_layouts", ())
    assert pl
    assert triggers.get("patch_layout") == pl


def test_local_context_window_tool_count_is_ratio_only(monkeypatch):
    from apps.backend.infrastructure.platform import config as cfg
    from apps.backend.infrastructure.agent_runtime.context_budget import completion_quotas_from_window

    monkeypatch.setattr(cfg.config, "AGENT_TOOLS_COUNT_CAP_RATIO", 0.0004)
    q = completion_quotas_from_window(32_768, source="test")
    assert q.max_tool_count == int(32_768 * 0.0004)


def test_build_tool_forward_plan_always_catalog(monkeypatch):
    from apps.backend.domain.agent_runtime.tool_schema import _registry_tool_spec_by_registered_name

    delegate_spec = _registry_tool_spec_by_registered_name("delegate")
    assert delegate_spec is not None
    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy.rank_tools_for_forward",
        lambda tools, text, triggers, **kw: (list(tools), False),
    )
    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="general",
            model_id="gpt-4o",
            context_window_tokens=128_000,
            user_text="Delegate research to a specialist sub-agent",
            tool_specs=[delegate_spec],
            ranking_enabled=False,
            full_schema_preference=True,
        )
    )
    assert plan.schema_mode_per_tool["delegate"] == "catalog"


def test_build_tool_forward_plan_pins_first(monkeypatch):
    specs = [_spec(n) for n in ("delegate", "catalog", "user_secrets_status", "rag_search", "web_search.search")]

    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy.rank_tools_for_forward",
        lambda tools, text, triggers, **kw: (list(reversed(tools)), True),
    )
    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy._pinned_tools_for_agent",
        lambda agent_id: frozenset({"delegate", "catalog", "user_secrets_status"}),
    )

    class _FakeReg:
        def get_agent(self, agent_id):
            return {"pinned_tools": ["delegate", "catalog", "user_secrets_status"]}

    monkeypatch.setattr(
        "apps.backend.domain.agent_runtime.registry.get_agent_registry",
        lambda: _FakeReg(),
    )

    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="general",
            model_id="qwen2.5:7b",
            context_window_tokens=262_144,
            user_text="delegate research task",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=False,
        )
    )
    assert plan.forward_names[:3] == ["delegate", "catalog", "user_secrets_status"]
    assert plan.pins_included == ["delegate", "catalog", "user_secrets_status"]
    assert plan.meta["pinned_count"] == 3
