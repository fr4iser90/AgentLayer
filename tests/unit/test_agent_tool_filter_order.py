"""Agent allowlist must narrow the pool before router intent filter (intersect, not replace)."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.platform import config as cfg
from apps.backend.domain.plugin_system.registry import reload_registry
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories,
    filter_merged_tools_by_categories_for_agent,
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
            "delegate",
            "rag_search",
        )
    ]
    general_allow = frozenset(
        {
            "list_available_tools",
            "get_tool_help",
            "list_tool_categories",
            "list_tools_in_category",
            "catalog",
            "delegate",
            "rag_search",
        }
    )
    after_agent = _intersect_agent_allowlist(pool, general_allow)
    assert len(after_agent) == 7

    after_router = filter_merged_tools_by_categories(after_agent, frozenset())
    names = {t["function"]["name"] for t in after_router}
    assert names == set(TOOL_INTROSPECTION)
    assert "catalog" not in names
    assert "delegate" not in names


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
            "delegate",
        }
    )
    all_specs = [_spec(n) for n in general_allow]
    rebuilt = [t for t in all_specs if t["function"]["name"] in general_allow]
    assert len(rebuilt) == 6
    assert len(pool) == 4
    assert len(rebuilt) > len(pool)


def test_general_allowlist_survives_knowledge_category_match() -> None:
    """Research-style prompt: router picks knowledge tools; general keeps delegate."""
    reload_registry()
    general_tools = [
        _spec(n)
        for n in (
            "delegate",
            "catalog",
            "user_secrets_status",
        )
    ]
    text = "Search the knowledge base for onboarding docs and summarize."
    cats = classify_user_tool_categories(text)
    after_router = filter_merged_tools_by_categories_for_agent(
        general_tools,
        cats,
        agent_has_explicit_allowlist=True,
    )
    names = {t["function"]["name"] for t in after_router}
    assert "delegate" in names
    assert "catalog" in names
    assert len(names) == 3


def test_research_agent_keeps_knowledge_tools() -> None:
    """research YAML allowlist includes rag_search and web search tools."""
    reload_registry()
    from apps.backend.domain.agent_runtime.registry import get_agent_registry
    from apps.backend.application.agent_runtime.runtime.prompts import _tool_spec_name
    from apps.backend.domain.plugin_system.registry import get_registry

    reg = get_registry()
    agent = get_agent_registry().get_agent("research")
    assert agent is not None
    merged = list(reg.chat_tool_specs)
    tool_names_agent = agent.get("tool_names", [])
    allowed_tool_names = frozenset(tool_names_agent)
    merged = [
        t
        for t in merged
        if (n := _tool_spec_name(t)) is None or n in allowed_tool_names
    ]
    names = {_tool_spec_name(t) for t in merged if _tool_spec_name(t)}
    assert "rag_search" in names
    assert "web_search.search" in names
    assert len(names) >= 10


def test_general_allowlist_survives_partial_category_match() -> None:
    """Messaging prompt: router matches comms tools; general keeps delegate too."""
    reload_registry()
    general_tools = [
        _spec(n)
        for n in (
            "delegate",
            "catalog",
            "user_secrets_status",
        )
    ]
    text = "Send a message to the team channel with today's summary."
    cats = classify_user_tool_categories(text)
    after_router = filter_merged_tools_by_categories_for_agent(
        general_tools,
        cats,
        agent_has_explicit_allowlist=True,
    )
    names = {t["function"]["name"] for t in after_router}
    assert "delegate" in names
    assert len(names) == 3
