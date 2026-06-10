"""Tests for dynamic tool forward policy (ranking cap, schema tiers — no pins)."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.tool_forward_policy import (
    ToolForwardContext,
    apply_schema_modes_to_specs,
    build_tool_forward_plan,
    build_tool_triggers_map,
    compute_tool_forward_limits,
    infer_model_tier,
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


def test_compute_tool_forward_limits_uses_context_budget():
    from apps.backend.core import config as cfg

    cfg.config.AGENT_TOOLS_BUDGET_RATIO = 0.06
    cfg.config.AGENT_TOOLS_COUNT_CAP_RATIO = 0.0004
    tok, count = compute_tool_forward_limits(context_window_tokens=128_000, model_tier="weak_local")
    assert tok == int(128_000 * 0.06)
    assert count == int(128_000 * 0.0004)
    tok0, count0 = compute_tool_forward_limits(context_window_tokens=0, model_tier="weak_local")
    assert tok0 == 0
    assert count0 == 0


def test_build_tool_forward_plan_uses_ranking_not_pins(monkeypatch):
    specs = [_spec(n) for n in ("dashboard.read", "propose_layouts", "patch_layout", "list", "other_a", "other_b")]

    class FakeReg:
        def get_agent(self, aid: str):
            return {
                "tool_names": [s["function"]["name"] for s in specs],
                "tool_forward_prefer_full_schema": ["dashboard.read", "propose_layouts"],
            }

    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy.get_agent_registry",
        lambda: FakeReg(),
    )
    monkeypatch.setattr(
        "apps.backend.domain.tool_forward_policy.rank_tools_for_forward",
        lambda tools, text, triggers, **kw: (list(reversed(tools)), True),
    )

    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="dashboard",
            model_id="qwen2.5:7b",
            context_window_tokens=262_144,
            model_tier="weak_local",
            user_text="zeig mir layout varianten",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=False,
        )
    )
    assert plan.pins_included == []
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
    from apps.backend.core import config as cfg
    from apps.backend.infrastructure.context_budget import completion_quotas_from_window

    monkeypatch.setattr(cfg.config, "AGENT_TOOLS_COUNT_CAP_RATIO", 0.0004)
    q = completion_quotas_from_window(32_768, source="test")
    assert q.max_tool_count == int(32_768 * 0.0004)
