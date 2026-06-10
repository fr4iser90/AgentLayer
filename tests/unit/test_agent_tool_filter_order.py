"""Agent allowlist must narrow the pool before router intent filter (intersect, not replace)."""

from __future__ import annotations

from typing import Any

from apps.backend.core import config as cfg
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    filter_merged_tools_by_categories,
)


def _spec(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": name, "description": name, "parameters": {"type": "object"}},
    }


def _intersect_agent_allowlist(tools: list[Any], allowed: frozenset[str]) -> list[Any]:
    return [t for t in tools if t["function"]["name"] in allowed]


def test_router_strict_after_agent_allowlist_keeps_minimal(monkeypatch):
    """Simulates planner order: merge → agent intersect → router categories."""
    monkeypatch.setattr(cfg.config, "AGENT_ROUTER_STRICT_DEFAULT", True)
    pool = [
        _spec(n)
        for n in (
            "list_available_tools",
            "get_tool_help",
            "list_tool_categories",
            "list_tools_in_category",
            "catalog",
            "bash",
            "read_file",
        )
    ]
    general_allow = frozenset(
        {
            "list_available_tools",
            "get_tool_help",
            "list_tool_categories",
            "list_tools_in_category",
            "catalog",
            "bash",
            "read_file",
        }
    )
    after_agent = _intersect_agent_allowlist(pool, general_allow)
    assert len(after_agent) == 7

    after_router = filter_merged_tools_by_categories(after_agent, frozenset())
    names = {t["function"]["name"] for t in after_router}
    assert names == set(TOOL_INTROSPECTION)
    assert "catalog" not in names
    assert "bash" not in names


def test_replacing_with_full_allowlist_would_break_router_minimal():
    """Document the old bug: rebuilding from allowlist ignores router minimal."""
    pool = [_spec(n) for n in TOOL_INTROSPECTION]
    general_allow = frozenset(
        {
            "list_available_tools",
            "get_tool_help",
            "list_tool_categories",
            "list_tools_in_category",
            "catalog",
            "bash",
        }
    )
    # Old code: after router minimal (4 tools), replace with all specs matching allowlist
    all_specs = [_spec(n) for n in general_allow]
    rebuilt = [t for t in all_specs if t["function"]["name"] in general_allow]
    assert len(rebuilt) == 6
    assert len(pool) == 4
    assert len(rebuilt) > len(pool)
