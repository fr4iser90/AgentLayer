"""Tests for unified retrieval tool ``retrieve_context``."""

from __future__ import annotations

import json
from unittest.mock import patch

import plugins.tools.workspace.search.retrieve_context as rc


def test_parse_sources_defaults() -> None:
    assert rc._parse_sources(None) == ["code_grep", "code_semantic", "docs"]
    assert rc._parse_sources(["memory", "code_grep"]) == ["memory", "code_grep"]


def test_retrieve_context_requires_query() -> None:
    out = json.loads(rc.retrieve_context({}))
    assert out["ok"] is False


def test_retrieve_context_requires_workspace_for_code() -> None:
    out = json.loads(rc.retrieve_context({"query": "auth"}, context=None))
    assert out["ok"] is False


def test_retrieve_context_merges_sub_retrievers() -> None:
    ctx = {"workspace": {"id": "ws-1", "path": "/tmp/ws"}}
    grep_payload = {"ok": True, "matches": [{"path": "a.py", "line": 1, "text": "auth"}]}
    sem_payload = {
        "ok": True,
        "results": [{"file_path": "b.py", "line": 2, "name": "login"}],
    }

    with (
        patch.object(rc, "coding_search", return_value=json.dumps(grep_payload)),
        patch.object(rc, "coding_semantic_search", return_value=json.dumps(sem_payload)),
        patch.object(rc, "_run_docs", return_value={"ok": True, "hits": [], "count": 0}),
        patch.object(
            rc.operator_settings,
            "rag_settings",
            return_value={"enabled": True},
        ),
    ):
        out = json.loads(
            rc.retrieve_context(
                {"query": "authentication", "sources": ["code_grep", "code_semantic", "docs"]},
                context=ctx,
            )
        )
    assert out["ok"] is True
    assert out["code_grep"]["matches"][0]["path"] == "a.py"
    assert out["code_semantic"]["results"][0]["name"] == "login"
    assert isinstance(out.get("fused_ranking"), list)
    assert len(out["fused_ranking"]) >= 1
    assert "next_steps" in out
    assert len(out["next_steps"]) >= 1


def test_run_docs_skipped_when_rag_disabled() -> None:
    with patch.object(
        rc.operator_settings,
        "rag_settings",
        return_value={"enabled": False},
    ):
        doc = rc._run_docs("q", 5, context=None, domain="agentlayer_docs")
    assert doc.get("skipped") is True
