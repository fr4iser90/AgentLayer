"""Tests for ``plugins/skills``-style skill plugin loading."""

from __future__ import annotations

from apps.backend.infrastructure.skill_plugins import collect_plugin_skills_markdown
from apps.backend.infrastructure.skills_prompt import load_combined_skills_prompt


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
    import apps.backend.core.config as cfg

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
