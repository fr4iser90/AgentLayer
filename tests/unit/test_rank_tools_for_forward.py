"""Tests for relevance-gated tool forward ranking."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_tools import rank_tools_for_forward
from apps.backend.domain.plugin_system.tool_routing import TOOL_INTROSPECTION


def _spec(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Tool {name}",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_gate_keeps_only_introspection_when_no_relevance(monkeypatch):
    tools = [
        _spec(n)
        for n in ("list_available_tools", "get_tool_help", "catalog", "read_file", "bash")
    ]
    monkeypatch.setattr(
        "apps.backend.domain.agent_tools.embed_one",
        lambda text: [1.0, 0.0] if "17" in text else [0.0, 1.0],
    )
    monkeypatch.setattr(
        "apps.backend.domain.agent_tools._tool_embedding_cache",
        {
            "list_available_tools": [0.5, 0.5],
            "get_tool_help": [0.5, 0.5],
            "catalog": [0.0, 1.0],
            "read_file": [0.0, 1.0],
            "bash": [0.0, 1.0],
        },
    )
    ranked, applied = rank_tools_for_forward(tools, "What is 17 + 25?", {})
    assert applied is True
    names = {t["function"]["name"] for t in ranked}
    assert names <= TOOL_INTROSPECTION
    assert "catalog" not in names
    assert "bash" not in names


def test_name_mention_forwards_action_tool(monkeypatch):
    tools = [_spec("list_available_tools"), _spec("catalog"), _spec("bash")]
    monkeypatch.setattr("apps.backend.domain.agent_tools.embed_one", lambda text: [0.1, 0.9])
    monkeypatch.setattr(
        "apps.backend.domain.agent_tools._tool_embedding_cache",
        {n: [0.1, 0.9] for n in ("list_available_tools", "catalog", "bash")},
    )
    ranked, _ = rank_tools_for_forward(tools, "Use the catalog tool to list tools.", {})
    names = [t["function"]["name"] for t in ranked]
    assert "catalog" in names


def test_category_routed_keeps_full_pool_sorted(monkeypatch):
    tools = [_spec(n) for n in ("a", "b", "c")]
    monkeypatch.setattr("apps.backend.domain.agent_tools.embed_one", lambda text: [1.0, 0.0])
    monkeypatch.setattr(
        "apps.backend.domain.agent_tools._tool_embedding_cache",
        {"a": [1.0, 0.0], "b": [0.5, 0.5], "c": [0.0, 1.0]},
    )
    ranked, applied = rank_tools_for_forward(
        tools, "github issue", {}, category_routed=True
    )
    assert applied is True
    assert len(ranked) == 3
