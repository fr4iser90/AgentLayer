"""Tests for ``plugins/skills``-style skill plugin loading."""

from __future__ import annotations

from apps.backend.infrastructure.plugins.skill_plugins import collect_plugin_skills_markdown
from apps.backend.infrastructure.plugins.skills_prompt import load_combined_skills_prompt


def test_collect_plugin_skills_from_markdown(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_SKILL_DIRS", str(tmp_path))
    (tmp_path / "one.md").write_text(
        "---\n"
        "skill_id: hello\n"
        "agents: coding\n"
        "---\n\n"
        "Line one.\n",
        encoding="utf-8",
    )
    assert "hello" in collect_plugin_skills_markdown("coding", max_chars=5000)
    assert "Line one" in collect_plugin_skills_markdown("coding", max_chars=5000)
    assert collect_plugin_skills_markdown("general", max_chars=5000) == ""


def test_collect_plugin_skills_respects_skill_agents(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AGENT_SKILL_DIRS", str(tmp_path))
    (tmp_path / "one.py").write_text(
        'SKILL_ID = "hello"\n'
        'SKILL_BODY = "Line one."\n'
        'SKILL_AGENTS = ("coding",)\n',
        encoding="utf-8",
    )
    assert "hello" in collect_plugin_skills_markdown("coding", max_chars=5000)
    assert "Line one" in collect_plugin_skills_markdown("coding", max_chars=5000)
    assert collect_plugin_skills_markdown("general", max_chars=5000) == ""


def test_load_combined_skills_includes_file(monkeypatch, tmp_path) -> None:
    import apps.backend.infrastructure.platform.config as cfg

    monkeypatch.setenv("AGENT_SKILL_DIRS", str(tmp_path))
    (tmp_path / "p.py").write_text(
        'SKILL_ID = "p1"\nSKILL_BODY = "from plugin"\n',
        encoding="utf-8",
    )
    extra = tmp_path / "extra.md"
    extra.write_text("from file", encoding="utf-8")
    monkeypatch.setattr(cfg, "AGENT_SKILLS_PROMPT_FILE", str(extra), raising=False)
    monkeypatch.setattr(cfg, "AGENT_SKILLS_MAX_TOTAL_CHARS", 8000, raising=False)
    out = load_combined_skills_prompt("coding_plan")
    assert "from plugin" in out
    assert "from file" in out
    assert "## Skills" in out


def test_general_loads_orchestrator_skills_from_repo() -> None:
    out = collect_plugin_skills_markdown("general", max_chars=50000)
    assert "orchestrator_delegate" in out
    assert "orchestrator_workspace" in out
    assert "coding_plan" in out
    coding_out = collect_plugin_skills_markdown("coding", max_chars=50000)
    assert "orchestrator_delegate" not in coding_out
    assert "coding_build_discipline" in coding_out


def test_domain_discipline_skills_from_repo() -> None:
    plan = collect_plugin_skills_markdown("coding_plan", max_chars=50000)
    assert "coding_plan_discipline" in plan
    assert "Read-only" in plan
    assert "secrets_handling" not in plan
    assert "tool_usage_discipline" in plan

    build = collect_plugin_skills_markdown("coding", max_chars=50000)
    assert "coding_build_discipline" in build
    assert "coding_fix_from_artifact" not in build

    sec = collect_plugin_skills_markdown("security_auditor", max_chars=50000)
    assert "security_auditor_discipline" in sec
    assert "SSC is source of truth" in sec

    dash = collect_plugin_skills_markdown("dashboard", max_chars=50000)
    assert "dashboard_discipline" in dash
    assert "propose_layouts" in dash
