"""Tests for discipline content loaded from ``plugins/skills``."""

from __future__ import annotations

from apps.backend.infrastructure.skill_plugins import (
    collect_plugin_skills_markdown,
    load_skill_text_by_id,
)
from apps.backend.infrastructure.skills_prompt import load_combined_skills_prompt


def test_research_gets_tool_usage_not_secrets() -> None:
    out = collect_plugin_skills_markdown("research", max_chars=50000)
    assert "tool_usage_discipline" in out
    assert "secrets_handling" not in out
    assert "secrets_orchestrator" not in out


def test_general_gets_orchestrator_secrets_not_full_handling() -> None:
    out = collect_plugin_skills_markdown("general", max_chars=50000)
    assert "secrets_orchestrator" in out
    assert "secrets_handling" not in out
    assert "tool_usage_discipline" not in out
    assert "orchestrator_delegate" in out


def test_coding_gets_secrets_handling_not_orchestrator() -> None:
    out = collect_plugin_skills_markdown("coding", max_chars=50000)
    assert "secrets_handling" in out
    assert "save_user_secret" in out
    assert "secrets_orchestrator" not in out


def test_security_auditor_gets_secrets_handling() -> None:
    out = collect_plugin_skills_markdown("security_auditor", max_chars=50000)
    assert "secrets_handling" in out


def test_math_gets_neither_secrets_skill() -> None:
    out = collect_plugin_skills_markdown("math", max_chars=50000)
    assert "secrets_handling" not in out
    assert "secrets_orchestrator" not in out


def test_coding_fix_from_artifact_only_with_delegate_mode() -> None:
    without = collect_plugin_skills_markdown("coding", max_chars=50000)
    assert "coding_fix_from_artifact" not in without

    with_mode = collect_plugin_skills_markdown(
        "coding", max_chars=50000, delegate_mode="fix_from_artifact"
    )
    assert "coding_fix_from_artifact" in with_mode


def test_dashboard_layout_nudge_loadable_by_id() -> None:
    text = load_skill_text_by_id("dashboard_layout_proposal_nudge")
    assert text
    assert "propose_layouts" in text


def test_load_combined_skills_passes_delegate_mode() -> None:
    out = load_combined_skills_prompt("coding", delegate_mode="fix_from_artifact")
    assert "coding_fix_from_artifact" in out
