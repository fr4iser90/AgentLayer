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


def test_compute_tool_forward_limits_uses_context_budget(monkeypatch):
    from apps.backend.infrastructure.platform import config as cfg
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    # The tools ratio is a runtime knob, so the registry default outranks the env constant.
    monkeypatch.setattr(ace, "context_tools_budget_ratio", lambda **_kw: 0.06)
    monkeypatch.setattr(cfg.config, "AGENT_TOOLS_COUNT_CAP_RATIO", 0.0004)
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
    assert all(m == "full" for m in plan.schema_mode_per_tool.values())
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


def test_build_tool_forward_plan_honours_schema_preference(monkeypatch):
    from apps.backend.domain.agent_runtime.tool_schema import _registry_tool_spec_by_registered_name

    delegate_spec = _registry_tool_spec_by_registered_name("delegate")
    assert delegate_spec is not None
    monkeypatch.setattr(
        "apps.backend.domain.tools.forward_policy.rank_tools_for_forward",
        lambda tools, text, triggers, **kw: (list(tools), False),
    )

    def _plan(full_schema: bool):
        return build_tool_forward_plan(
            ToolForwardContext(
                agent_id="general",
                model_id="gpt-4o",
                context_window_tokens=128_000,
                user_text="Delegate research to a specialist sub-agent",
                tool_specs=[delegate_spec],
                ranking_enabled=False,
                full_schema_preference=full_schema,
            )
        )

    assert _plan(True).schema_mode_per_tool["delegate"] == "full"
    assert _plan(False).schema_mode_per_tool["delegate"] == "catalog"


def _no_pins(monkeypatch) -> None:
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


def _plan_for_allowlist(monkeypatch, *, has_explicit_allowlist: bool):
    _no_pins(monkeypatch)
    specs = [_spec(n) for n in ("bash", "edit", "apply_patch", "git_read", "lsp")]
    return build_tool_forward_plan(
        ToolForwardContext(
            agent_id="coding",
            model_id="qwen2.5:7b",
            context_window_tokens=262_144,
            # Mentions no tool name and matches no trigger — every tool scores 0.
            user_text="fix the login bug",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=True,
            has_explicit_allowlist=has_explicit_allowlist,
        )
    )


def test_declared_allowlist_survives_irrelevant_user_text(monkeypatch):
    plan = _plan_for_allowlist(monkeypatch, has_explicit_allowlist=True)
    assert sorted(plan.forward_names) == ["apply_patch", "bash", "edit", "git_read", "lsp"]


def test_router_pool_still_drops_irrelevant_tools(monkeypatch):
    plan = _plan_for_allowlist(monkeypatch, has_explicit_allowlist=False)
    # Nothing scored, so the ranker falls back to the ordered pool rather than an empty list.
    assert plan.forward_names
    assert plan.ranking_applied is True


def test_token_budget_still_bounds_a_declared_allowlist(monkeypatch):
    _no_pins(monkeypatch)
    from apps.backend.infrastructure.platform import config as cfg

    monkeypatch.setattr(cfg.config, "AGENT_TOOLS_BUDGET_RATIO", 0.01)
    monkeypatch.setattr(cfg.config, "AGENT_TOOLS_COUNT_CAP_RATIO", 0.01)
    specs = [_spec(f"tool_{i}") for i in range(60)]
    plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id="coding",
            model_id="qwen2.5:7b",
            context_window_tokens=8_192,
            user_text="fix the login bug",
            tool_specs=specs,
            ranking_enabled=True,
            full_schema_preference=True,
            has_explicit_allowlist=True,
        )
    )
    assert 0 < len(plan.forward_names) < 60


def test_estimate_tracks_the_rendered_schema_mode():
    from apps.backend.domain.tools.forward_policy import _estimate_tool_spec_tokens
    from apps.backend.domain.agent_runtime.tool_schema import _registry_tool_spec_by_registered_name

    spec = _registry_tool_spec_by_registered_name("delegate")
    assert spec is not None
    full = _estimate_tool_spec_tokens(spec, schema_mode="full")
    catalog = _estimate_tool_spec_tokens(spec, schema_mode="catalog")
    assert full != catalog


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
