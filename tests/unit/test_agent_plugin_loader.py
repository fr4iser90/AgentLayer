"""Tests for YAML agent plugin loader."""

from __future__ import annotations

from apps.backend.infrastructure.platform.config import PLUGINS_DIR
from apps.backend.domain.agent_runtime.plugin_loader import definition_from_yaml, discover_yaml_agents


def test_discover_yaml_agents_finds_built_ins() -> None:
    pairs = discover_yaml_agents(PLUGINS_DIR / "agents")
    ids = {p.parent.name for _, p in pairs}
    assert "general" in ids
    assert "research" in ids
    assert "coding" not in ids


def test_definition_from_yaml_research() -> None:
    agent_dir = PLUGINS_DIR / "agents" / "research"
    d = definition_from_yaml(agent_dir, agent_dir / "agent.yaml")
    assert d is not None
    assert d["id"] == "research"
    assert d["source_kind"] == "yaml"
    assert d.get("tool_allowlist")
    assert "web_search.search" in d["tool_allowlist"]
    assert "bash" not in d["tool_allowlist"]
