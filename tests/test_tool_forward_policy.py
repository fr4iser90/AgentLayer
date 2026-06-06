"""Tests for dynamic tool forward policy (pins, ranking cap, schema tiers)."""

from __future__ import annotations

from typing import Any

import pytest

from apps.backend.domain.tool_forward_policy import (
    ToolForwardContext,
    apply_schema_modes_to_specs,
    build_tool_forward_plan,
    build_tool_triggers_map,
    compute_tool_forward_limits,
    dashboard_layout_proposal_nudge_needed,
    infer_model_tier,
    is_propose_layouts_tool,
    layout_proposal_intent,
    pinned_tools_for_agent,
    resolve_pin_names,
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


def test_infer_model_tier():
    assert infer_model_tier(model_id="qwen2.5:7b", catalog_owned_by="ollama") == "weak_local"
    assert infer_model_tier(model_id="gpt-4o", catalog_owned_by="openai") == "strong"
    assert infer_model_tier(model_id="custom", catalog_owned_by="") == "standard"


def test_compute_tool_forward_limits_uses_tier_cap():
    tok, count = compute_tool_forward_limits(context_window_tokens=128_000, model_tier="weak_local")
    assert tok >= 4000
    assert count == 10
    _, legacy_count = compute_tool_forward_limits(context_window_tokens=0, model_tier="weak_local")
    assert legacy_count >= 1


def test_resolve_pin_names_filters_allowlist(monkeypatch):
    class FakeReg:
        def get_agent(self, aid: str):
            if aid != "dashboard":
                return None
            return {
                "tool_names": ["dashboard.read", "propose_layouts", "patch_layout", "other"],
                "pinned_tools": ["dashboard.read", "propose_layouts", "missing_tool"],
            }

    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy.get_agent_registry",
        lambda: FakeReg(),
    )
    pins = resolve_pin_names("dashboard", ("patch_data",))
    assert pins == frozenset({"dashboard.read", "propose_layouts"})


def test_build_tool_forward_plan_pins_dashboard_tools(monkeypatch):
    specs = [_spec(n) for n in ("dashboard.read", "propose_layouts", "patch_layout", "list", "other_a", "other_b")]

    class FakeReg:
        def get_agent(self, aid: str):
            return {
                "tool_names": [s["function"]["name"] for s in specs],
                "pinned_tools": ["dashboard.read", "propose_layouts", "patch_layout", "patch_data", "list"],
                "tool_forward_prefer_full_schema": ["dashboard.read", "propose_layouts"],
            }

    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy.get_agent_registry",
        lambda: FakeReg(),
    )
    monkeypatch.setattr(
        "apps.backend.domain.agent_tools._pinned_tools_for_agent",
        lambda aid: frozenset({"dashboard.read", "propose_layouts", "patch_layout", "list"}),
    )
    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy._rank_tools_by_user_input",
        lambda tools, text, triggers: list(reversed(tools)),
    )

    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="dashboard",
            model_id="qwen2.5:7b",
            context_window_tokens=32_000,
            model_tier="weak_local",
            user_text="zeig mir layout varianten",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=False,
        )
    )
    assert "dashboard.read" in plan.forward_names
    assert "propose_layouts" in plan.forward_names
    assert plan.pins_included
    assert len(plan.forward_names) <= plan.max_tool_count


def test_layout_intent_adds_pins(monkeypatch):
    specs = [_spec("dashboard.read"), _spec("propose_layouts"), _spec("zzz")]

    monkeypatch.setattr(
        "apps.backend.domain.agent_tools._pinned_tools_for_agent",
        lambda aid: frozenset(),
    )
    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy._rank_tools_by_user_input",
        lambda tools, text, triggers: tools,
    )

    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id=None,
            model_id="m",
            context_window_tokens=16_000,
            model_tier="standard",
            user_text="bitte layout vorschläge",
            tool_specs=specs,
            ranking_enabled=False,
            full_schema_preference=False,
        )
    )
    assert "dashboard.read" in plan.forward_names
    assert "propose_layouts" in plan.forward_names


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


def test_build_tool_triggers_map_includes_extras():
    triggers = build_tool_triggers_map(["propose_layouts", "patch_layout"])
    assert "layout" in triggers.get("propose_layouts", ())
    assert "grid" in triggers.get("patch_layout", ())


def test_layout_proposal_intent_german_variants():
    assert layout_proposal_intent("Zeig mir 3 Layout-Varianten")
    assert not layout_proposal_intent("wie viele projekte habe ich")


def test_dashboard_layout_proposal_nudge_needed():
    names = frozenset({"dashboard.read", "propose_layouts", "patch_layout"})
    assert dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=0,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=True,
        nudge_count=0,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=2,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="coding",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=0,
        forwarded_tool_names=names,
    )


def test_is_propose_layouts_tool():
    assert is_propose_layouts_tool("propose_layouts")
    assert is_propose_layouts_tool("dashboard.propose_layouts")
    assert not is_propose_layouts_tool("patch_layout")


def test_pinned_tools_for_agent_dashboard(monkeypatch):
    class FakeReg:
        def get_agent(self, aid: str):
            return {
                "tool_names": ["dashboard.read", "propose_layouts"],
                "pinned_tools": ["dashboard.read"],
            }

    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy.get_agent_registry",
        lambda: FakeReg(),
    )
    assert pinned_tools_for_agent("dashboard") == frozenset({"dashboard.read"})
