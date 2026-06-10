"""Co-located plugin router phrase packs (*.router.yaml)."""

from __future__ import annotations

from pathlib import Path

from apps.backend.domain.plugin_system.registry import get_registry, reload_registry
from apps.backend.domain.plugin_system.router_phrases import load_co_located_router_phrases
from apps.backend.domain.plugin_system.tool_routing import classify_user_tool_categories


def test_load_co_located_router_phrases(tmp_path: Path) -> None:
    py = tmp_path / "sample.py"
    py.write_text("# tool\n", encoding="utf-8")
    yml = tmp_path / "sample.router.yaml"
    yml.write_text(
        """
domain: repository
phrases:
  en: [read file, readme]
  de: [datei lesen]
""".strip(),
        encoding="utf-8",
    )
    domain, phrases = load_co_located_router_phrases(f"file:{py}")
    assert domain == "repository"
    assert "read file" in phrases
    assert "datei lesen" in phrases


def test_read_file_yaml_merged_into_repository_triggers() -> None:
    reload_registry()
    reg = get_registry()
    triggers = reg.domain_trigger_substrings("repository")
    assert "read_file" in triggers
    assert "datei lesen" in triggers


def test_s3_prompt_matches_repository_via_co_located_yaml() -> None:
    text = (
        "Use read_file to read README.md in the bound workspace root. "
        "Reply with the first line of the file."
    )
    cats = classify_user_tool_categories(text)
    assert "repository" in cats


def test_german_read_prompt_matches_repository() -> None:
    reload_registry()
    cats = classify_user_tool_categories("Bitte lies die Datei README.md im Workspace.")
    assert "repository" in cats
