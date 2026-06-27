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


def test_general_allowlist_survives_repository_category_mismatch() -> None:
    """S3-style prompt: router picks repository tools; general orchestrator keeps delegate."""
    reload_registry()
    general_tools = [
        _spec(n)
        for n in (
            "delegate",
            "catalog",
            "workspace.create",
            "workspace.list",
            "bind",
            "user_secrets_status",
        )
    ]
    text = "Read README.md at the repository root and reply with the first line."
    cats = classify_user_tool_categories(text)
    assert "repository" in cats
    after_router = filter_merged_tools_by_categories_for_agent(
        general_tools,
        cats,
        agent_has_explicit_allowlist=True,
    )
    names = {t["function"]["name"] for t in after_router}
    assert "delegate" in names
    assert "catalog" in names
    assert len(names) == 6


def test_explicit_allowlist_agent_keeps_repository_tools_despite_coding_domain() -> None:
    """coding_plan/coding YAML allowlists repository.* tools; domain=coding must not strip them first."""
    reload_registry()
    from apps.backend.domain.agent_runtime.registry import get_agent_registry
    from apps.backend.application.agent_runtime.runtime.prompts import _tool_spec_name
    from apps.backend.domain.plugin_system.registry import get_registry
    from apps.backend.domain.plugin_system.tool_routing import filter_merged_tools_by_domain

    reg = get_registry()
    agent = get_agent_registry().get_agent("coding_plan")
    assert agent is not None
    merged = list(reg.chat_tool_specs)
    agent_has_explicit_allowlist = bool(agent.get("tool_allowlist"))
    tool_domain_agent = agent.get("tool_domain")
    tool_names_agent = agent.get("tool_names", [])
    if tool_domain_agent and not agent_has_explicit_allowlist:
        merged = filter_merged_tools_by_domain(merged, tool_domain_agent)
    if tool_names_agent:
        allowed_tool_names = frozenset(tool_names_agent)
        merged = [
            t
            for t in merged
            if (n := _tool_spec_name(t)) is None or n in allowed_tool_names
        ]
    names = {_tool_spec_name(t) for t in merged if _tool_spec_name(t)}
    assert "repository.read_file" in names
    assert len(names) >= 10


def test_general_allowlist_survives_partial_category_match() -> None:
    """W1-style prompt: router matches workspace tools only; general keeps delegate too."""
    reload_registry()
    general_tools = [
        _spec(n)
        for n in (
            "delegate",
            "catalog",
            "workspace.create",
            "workspace.list",
            "bind",
            "user_secrets_status",
        )
    ]
    text = (
        'Clone the Git repository https://github.com/octocat/Hello-World.git (branch master) '
        'into a new workspace named exactly "bench-git" and bind it. '
        "Read README.md at the repository root and reply with the first non-empty line."
    )
    cats = classify_user_tool_categories(text)
    after_router = filter_merged_tools_by_categories_for_agent(
        general_tools,
        cats,
        agent_has_explicit_allowlist=True,
    )
    names = {t["function"]["name"] for t in after_router}
    assert "delegate" in names
    assert "workspace.create" in names
    assert len(names) == 6
