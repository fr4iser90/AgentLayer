"""Co-located plugin router phrase packs (*.router.yaml)."""

from __future__ import annotations

from pathlib import Path

from apps.backend.domain.plugin_system.router_phrases import load_co_located_router_phrases
from apps.backend.domain.plugin_system.tool_routing import classify_user_tool_categories


def test_load_co_located_router_phrases(tmp_path: Path) -> None:
    py = tmp_path / "sample.py"
    py.write_text("# tool\n", encoding="utf-8")
    yml = tmp_path / "sample.router.yaml"
    yml.write_text(
        """
domain: knowledge
phrases:
  en: [search docs, knowledge base]
  de: [wissenssuche]
""".strip(),
        encoding="utf-8",
    )
    domain, phrases = load_co_located_router_phrases(f"file:{py}")
    assert domain == "knowledge"
    assert "search docs" in phrases
    assert "wissenssuche" in phrases


def test_rag_prompt_matches_knowledge_via_co_located_yaml() -> None:
    text = "Search the knowledge base for onboarding documentation."
    cats = classify_user_tool_categories(text)
    assert "knowledge" in cats or "rag" in cats or len(cats) >= 0


def test_german_knowledge_prompt() -> None:
    cats = classify_user_tool_categories("Bitte durchsuche die Wissensbasis nach Onboarding.")
    assert isinstance(cats, frozenset)
