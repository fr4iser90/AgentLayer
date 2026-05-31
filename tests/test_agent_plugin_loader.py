"""Tests for YAML agent plugin loader."""

from __future__ import annotations

from apps.backend.core.config import PLUGINS_DIR
from apps.backend.domain.agent_plugin_loader import definition_from_yaml, discover_yaml_agents


def test_discover_yaml_agents_finds_built_ins() -> None:
    pairs = discover_yaml_agents(PLUGINS_DIR / "agents")
    ids = {p.parent.name for _, p in pairs}
    assert "general" in ids
    assert "coding" in ids


def test_definition_from_yaml_coding_plan() -> None:
    agent_dir = PLUGINS_DIR / "agents" / "coding_plan"
    d = definition_from_yaml(agent_dir, agent_dir / "agent.yaml")
    assert d is not None
    assert d["id"] == "coding_plan"
    assert d["source_kind"] == "yaml"
    assert "workspace" in d["tool_domains"]
    assert "coding.read" in d["tool_capability_any"]
    assert "Plan" in d["system_prompt"]
    assert "bash" in d["system_prompt"]
