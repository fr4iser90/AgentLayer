"""Unit tests for agent config effective resolution and fingerprint."""

from __future__ import annotations

from apps.backend.infrastructure.agent_runtime import (
    agent_config_effective,
    agent_config_fingerprint,
    agent_config_task_intent,
)


def test_effective_max_tool_rounds_registry_default(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {})
    assert agent_config_effective.max_tool_rounds(tenant_id=1) == 20


def test_effective_value_uses_registry_default_for_pinned_tools(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {})
    val, src = agent_config_effective.effective_value("agent.general.pinned_tools", tenant_id=1)
    assert src == "registry_default"
    assert val is None


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
    from apps.backend.infrastructure.agent_runtime.agent_config_service import validate_patches

    out = validate_patches([{"knob_id": "not.real", "value": 1}])
    assert out["valid"] is False


def test_validate_patches_rejects_rubric_knob():
    from apps.backend.infrastructure.agent_runtime.agent_config_service import validate_patches

    out = validate_patches([{"knob_id": "rubric.s1_tool_catalog", "value": "x"}])
    assert out["valid"] is False
    assert out["errors"][0]["error"] == "not_writable"


def test_is_harness_knob_excludes_rubrics():
    from apps.backend.domain.agent_runtime.config_registry import is_harness_knob, knob_by_id

    assert is_harness_knob(knob_by_id("agent.max_tool_rounds") or {}) is True
    assert is_harness_knob(knob_by_id("rubric.s1_tool_catalog") or {}) is False
    assert is_harness_knob(knob_by_id("bench.harness_preset") or {}) is False


def test_context_tools_budget_ratio_db_override(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {"context.tools_budget_ratio": 0.12})
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)
    assert agent_config_effective.context_tools_budget_ratio(tenant_id=1) == 0.12


def test_coding_agent_yaml_overlay(monkeypatch):
    monkeypatch.setattr(
        agent_config_effective,
        "_cached_overrides",
        lambda _tid: {
            "agent.coding.tool_discipline_preset": "coding_plan",
            "agent.coding.coding_tools_permission_ask": True,
        },
    )
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)
    overlay = agent_config_effective.agent_yaml_overlay("coding", tenant_id=1)
    assert overlay["tool_discipline_preset"] == "coding_plan"
    assert overlay["coding_tools_permission_ask"] is True


def test_delegate_allowed_modes_filter(monkeypatch):
    monkeypatch.setattr(
        agent_config_effective,
        "_cached_overrides",
        lambda _tid: {"delegate.allowed_modes": ["fix_from_artifact"]},
    )
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)
    assert agent_config_effective.delegate_mode_allowed("fix_from_artifact", tenant_id=1) is True
    assert agent_config_effective.delegate_mode_allowed("git_forensics", tenant_id=1) is False


def test_validate_patches_accepts_number_knob():
    from apps.backend.infrastructure.agent_runtime.agent_config_service import validate_patches

    out = validate_patches([{"knob_id": "context.tools_budget_ratio", "value": 0.08}])
    assert out["valid"] is True


def test_task_intent_overlay_disabled_by_default():
    matches = agent_config_task_intent.match_task_intents("clone repository and read readme", tenant_id=1)
    assert matches == []


def test_task_intent_overlay_matches_registry_default(monkeypatch):
    monkeypatch.setattr(
        agent_config_effective,
        "_cached_overrides",
        lambda _tid: {"tool_routing.task_intent_overlay_enabled": True},
    )
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)

    matches = agent_config_task_intent.match_task_intents(
        "Please clone repository and read the README first line",
        tenant_id=1,
    )

    assert matches
    assert "workspace_clone_read" in {m.intent_id for m in matches}
    assert "workspace" in agent_config_task_intent.categories_for_matches(matches)
    assert "workspace.create" in agent_config_task_intent.tools_for_matches(matches)


def test_knowledge_orchestration_defaults_off(monkeypatch):
    monkeypatch.setattr(agent_config_effective, "_cached_overrides", lambda _tid: {})
    assert agent_config_effective.knowledge_orchestration_enabled(tenant_id=1) is False


def test_knowledge_orchestration_prompt_does_not_toggle_project_rag(monkeypatch):
    from apps.backend.infrastructure.memory.knowledge_orchestration_prompt import (
        build_knowledge_orchestration_snippet,
    )

    monkeypatch.setattr(
        agent_config_effective,
        "_cached_overrides",
        lambda _tid: {
            "knowledge.orchestration_enabled": True,
            "knowledge.orchestration_mode": "agent_native",
        },
    )
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)

    snippet = build_knowledge_orchestration_snippet(tenant_id=1)
    assert "K1-lite" in snippet
    assert "Do not enable or disable project RAG" in snippet


def test_knowledge_extractor_effective_knobs(monkeypatch):
    monkeypatch.setattr(
        agent_config_effective,
        "_cached_overrides",
        lambda _tid: {
            "knowledge.extractor_backend": "hybrid",
            "knowledge.extractor_provider_id": "agents-k1",
            "knowledge.extractor_model": "InternScience/Agents-K1",
        },
    )
    monkeypatch.setattr(agent_config_effective.db, "pool_ready", lambda: True)

    assert agent_config_effective.knowledge_extractor_backend(tenant_id=1) == "hybrid"
    assert agent_config_effective.knowledge_extractor_provider_id(tenant_id=1) == "agents-k1"
    assert agent_config_effective.knowledge_extractor_model(tenant_id=1) == "InternScience/Agents-K1"


def test_merge_agent_definition_without_db_pool():
    from apps.backend.domain.agent_runtime.registry import get_agent_registry
    from apps.backend.infrastructure.db import db

    assert not db.pool_ready()
    agent = get_agent_registry().get_agent("general")
    assert agent is not None
    assert agent.get("id") == "general"
