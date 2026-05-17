"""Tests for agent tool pattern matching (``AGENT_TOOL_PATTERNS`` resolution)."""

from __future__ import annotations

from apps.backend.domain.agent_registry import _match_tool, _tools_for_patterns


def test_match_prefix_dot_star() -> None:
    assert _match_tool("coding_read_file", ["coding.*"])
    assert not _match_tool("fs_read", ["coding.*"])


def test_match_operator_glob_underscore_star() -> None:
    assert _match_tool("operator_settings_get", ["operator_settings_*"])
    assert _match_tool("admin_tenants_list", ["admin_*"])
    assert not _match_tool("coding_bash", ["admin_*"])


def test_tools_for_patterns_dedup_order_preserved() -> None:
    names = ["admin_x", "operator_settings_get", "list_tools", "coding_read_file"]
    pats = ("admin_*", "operator_settings_*", "list_tools")
    out = _tools_for_patterns(list(pats), names)
    assert out == ["admin_x", "operator_settings_get", "list_tools"]


def test_coding_agent_uses_registry_domains_not_name_patterns() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("coding")
    assert a is not None
    names = a["tool_names"]
    assert "coding_read_file" in names
    assert "project_explain" in names
    assert "list_available_tools" not in names


def test_operator_agent_matches_capabilities() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("operator")
    assert a is not None
    names = a["tool_names"]
    assert "operator_settings_get" in names
    assert "rag_search" in names
    assert "schedule_job_list" in names


def test_security_auditor_agent_resolves_domains_and_rag_capability() -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    a = get_agent_registry().get_agent("security_auditor")
    assert a is not None
    names = a["tool_names"]
    assert "coding_read_file" in names
    assert "project_explain" in names
    assert "rag_search" in names


def test_agent_behavior_flags_come_from_plugins_not_ids() -> None:
    from apps.backend.domain.agent import _agent_behavior_flags

    c = _agent_behavior_flags("coding")
    assert c["coding_tools_permission_ask"] is True
    assert c["strict_workspace"] is False
    assert c["tool_discipline_preset"] == "coding_build"

    p = _agent_behavior_flags("coding_plan")
    assert p["strict_workspace"] is True
    assert p["coding_tools_permission_ask"] is True
    assert p["tool_discipline_preset"] == "coding_plan"

    s = _agent_behavior_flags("security_auditor")
    assert s["strict_workspace"] is True
