"""Unit tests for agent config effective resolution and fingerprint."""

from __future__ import annotations

from apps.backend.infrastructure import agent_config_effective, agent_config_fingerprint


def test_effective_max_tool_rounds_registry_default(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {})
    assert agent_config_effective.max_tool_rounds(tenant_id=1) == 20


def test_effective_value_uses_file_default_for_pinned_tools(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {})
    val, src = agent_config_effective.effective_value("agent.general.pinned_tools", tenant_id=1)
    assert src == "file_default"
    assert isinstance(val, list)
    assert "catalog" in val


def test_effective_db_override(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {"agent.max_tool_rounds": 99})
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)
    assert agent_config_effective.max_tool_rounds(tenant_id=1) == 99


def test_fingerprint_stable_for_same_state(monkeypatch):
    monkeypatch.setattr(agent_config_fingerprint, "deployment_git_sha", lambda: "abc123")
    monkeypatch.setattr(
        agent_config_fingerprint,
        "benchmark_sensitive_effective_map",
        lambda *, tenant_id: {"agent.max_tool_rounds": {"value": 8, "source": "registry_default"}},
    )
    a = agent_config_fingerprint.compute_fingerprint(tenant_id=1)
    b = agent_config_fingerprint.compute_fingerprint(tenant_id=1)
    assert a == b
    assert a.startswith("sha256:")


def test_validate_patches_rejects_unknown_knob():
    from apps.backend.infrastructure.agent_config_service import validate_patches

    out = validate_patches([{"knob_id": "not.real", "value": 1}])
    assert out["valid"] is False


def test_validate_patches_rejects_rubric_knob():
    from apps.backend.infrastructure.agent_config_service import validate_patches

    out = validate_patches([{"knob_id": "rubric.s1_tool_catalog", "value": "x"}])
    assert out["valid"] is False
    assert out["errors"][0]["error"] == "not_writable"


def test_is_harness_knob_excludes_rubrics():
    from apps.backend.domain.agent_config_registry import is_harness_knob, knob_by_id

    assert is_harness_knob(knob_by_id("agent.max_tool_rounds") or {}) is True
    assert is_harness_knob(knob_by_id("rubric.s1_tool_catalog") or {}) is False
    assert is_harness_knob(knob_by_id("bench.harness_preset") or {}) is False


def test_merge_agent_definition_without_db_pool():
    from apps.backend.domain.agent_registry import get_agent_registry
    from apps.backend.infrastructure.db import db

    assert not db.pool_ready()
    agent = get_agent_registry().get_agent("general")
    assert agent is not None
    assert agent.get("id") == "general"
