"""K1-lite workspace knowledge extraction."""

from __future__ import annotations

from apps.backend.infrastructure.workspace.workspace_k1_lite import (
    build_workspace_knowledge_units,
    extract_knowledge_units_for_file,
)


def test_extract_doc_headings_claims_and_evidence(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "# Auth Service\n\n"
        "- Tokens must expire after one hour.\n"
        "- The login endpoint returns a session cookie.\n",
        encoding="utf-8",
    )

    units = extract_knowledge_units_for_file(tmp_path, readme)

    assert any(u["kind"] == "entity" and "Auth Service" in u["text"] for u in units)
    assert any(u["kind"] == "claim" and "must expire" in u["text"] for u in units)
    assert any(u["kind"] == "evidence" and "session cookie" in u["text"] for u in units)


def test_extract_code_entities_and_claims(tmp_path):
    src = tmp_path / "service.py"
    src.write_text(
        "class AuthService:\n"
        "    # TODO: refresh tokens should rotate\n"
        "    def login(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    units = extract_knowledge_units_for_file(tmp_path, src)

    assert any(u["kind"] == "entity" and "class AuthService" in u["text"] for u in units)
    assert any(u["kind"] == "claim" and "refresh tokens" in u["text"] for u in units)


def test_build_workspace_knowledge_units_skips_node_modules(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.md").write_text("# Ignore me\n", encoding="utf-8")
    (tmp_path / "docs.md").write_text("# Keep me\n", encoding="utf-8")

    out = build_workspace_knowledge_units(tmp_path)

    paths = {path for path, _units in out}
    assert "docs.md" in paths
    assert "node_modules/ignored.md" not in paths


def test_hybrid_merges_llm_units(monkeypatch, tmp_path):
    doc = tmp_path / "README.md"
    doc.write_text("# Keep me\n", encoding="utf-8")

    def fake_llm(*_args, **_kwargs):
        return [
            {
                "kind": "claim",
                "label": "LLM claim",
                "text": "The project should keep evidence traceable.",
                "line": 1,
                "section": "Keep me",
                "source": "llm_extractor",
            }
        ]

    monkeypatch.setattr("apps.backend.infrastructure.workspace.workspace_k1_lite._llm_units_for_file", fake_llm)

    out = build_workspace_knowledge_units(tmp_path, extractor_backend="hybrid")

    units = [u for _path, path_units in out for u in path_units]
    assert any(u["source"] == "doc_heading" for u in units)
    assert any(u["source"] == "llm_extractor" for u in units)

