"""Tests for YAML agent plugin loader."""

from __future__ import annotations

from apps.backend.infrastructure.platform.config import PLUGINS_DIR
from apps.backend.domain.agent_runtime.plugin_loader import definition_from_yaml, discover_yaml_agents


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
    assert d.get("tool_allowlist")
    assert "repository.read_file" in d["tool_allowlist"]
    assert "bash" not in d["tool_allowlist"]
    assert "Plan" in d["system_prompt"]
    assert "bash" in d["system_prompt"]


def test_external_runtime_defaults_to_internal_loop() -> None:
    """Agents without ``external_runtime`` keep running in AgentLayer's planner loop."""
    for agent_id in ("general", "coding", "coding_plan"):
        agent_dir = PLUGINS_DIR / "agents" / agent_id
        d = definition_from_yaml(agent_dir, agent_dir / "agent.yaml")
        assert d is not None
        assert d.get("external_runtime") in (None, "")


def test_definition_from_yaml_coding_qwen_declares_external_runtime() -> None:
    agent_dir = PLUGINS_DIR / "agents" / "coding_qwen"
    d = definition_from_yaml(agent_dir, agent_dir / "agent.yaml")
    assert d is not None
    assert d["external_runtime"] == "qwen_code"
    # A build-capable external agent stays workspace-bound; unattended scheduled builds
    # with it are out of scope, so it is not schedulable. It is reachable via chat + delegate.
    assert d["requires_workspace"] is True
    assert d["strict_workspace"] is True
    assert d["delegatable"] is True
    assert d["schedulable"] is False
    assert "git push" in d["system_prompt"]
