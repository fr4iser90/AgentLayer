"""Workspace-scoped doc RAG retrieval."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from plugins.tools.capabilities.coding import retrieve_context as rc


def test_run_docs_workspace_scope_calls_search_with_workspace_id() -> None:
    ws_id = str(uuid.uuid4())
    ctx = {"workspace": {"id": ws_id, "path": "/tmp/ws", "docs_rag_enabled": True}}
    fake_hits = [
        {
            "title": "README.md",
            "content": "hello",
            "chunk_index": 0,
            "distance": 0.1,
            "domain": "workspace_docs",
        }
    ]

    with (
        patch.object(
            rc.operator_settings,
            "rag_settings",
            return_value={"enabled": True},
        ),
        patch(
            "apps.backend.infrastructure.rag.rag.search_for_identity",
            return_value=fake_hits,
        ) as mock_search,
    ):
        out = rc._run_docs("setup", 5, context=ctx, domain="agentlayer_docs")

    assert out["ok"] is True
    assert out["scope"] == "workspace"
    mock_search.assert_called_once()
    _args, kwargs = mock_search.call_args
    assert kwargs.get("workspace_id") == uuid.UUID(ws_id)
    assert "domain" not in kwargs or kwargs.get("domain") is None


def test_retrieve_context_docs_not_mixed_with_agentlayer_when_workspace_bound() -> None:
    ws_id = str(uuid.uuid4())
    ctx = {"workspace": {"id": ws_id, "path": "/tmp/ws", "docs_rag_enabled": True}}

    with (
        patch.object(rc, "coding_search", return_value=json.dumps({"ok": True, "matches": []})),
        patch.object(
            rc, "coding_semantic_search", return_value=json.dumps({"ok": True, "results": []})
        ),
        patch.object(
            rc,
            "_run_docs",
            return_value={"ok": True, "scope": "workspace", "hits": [], "count": 0},
        ) as mock_docs,
        patch.object(
            rc.operator_settings,
            "rag_settings",
            return_value={"enabled": True},
        ),
    ):
        out = json.loads(
            rc.retrieve_context(
                {"query": "auth", "sources": ["docs"], "domain": "agentlayer_docs"},
                context=ctx,
            )
        )
    mock_docs.assert_called_once()
    _args, kwargs = mock_docs.call_args
    assert kwargs.get("domain") == "agentlayer_docs"
    assert out["docs"]["scope"] == "workspace"
