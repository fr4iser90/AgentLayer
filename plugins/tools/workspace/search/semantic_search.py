"""Semantic code search via Qdrant vector similarity."""

from __future__ import annotations

import json
from typing import Any, Callable

from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
    workspace_retrieval_flags,
)

try:
    from apps.backend.infrastructure.codebase.code_index_qdrant import get_code_index

    _HAS_QDRANT = True
except ImportError:
    _HAS_QDRANT = False


__version__ = "1.0.0"
TOOL_ID = "semantic_search"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
# Router phrases: co-located semantic_search.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Semantic Search"
TOOL_DESCRIPTION = (
    "Semantic search of code symbols using vector embeddings in Qdrant. "
    "More powerful than keyword search - finds symbols by meaning rather than exact match. "
    "Requires prior indexing via coding_index."
)

_DEFAULT_LIMIT = 20


def semantic_search(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not _HAS_QDRANT:
        return json.dumps(
            {
                "ok": False,
                "error": "Qdrant not available. Set QDRANT_URL in environment.",
            },
            ensure_ascii=False,
        )
    query = arguments.get("query")
    if not query or not str(query).strip():
        return json.dumps(
            {"ok": False, "error": "query is required"},
            ensure_ascii=False,
        )
    kind = arguments.get("kind")
    limit = int(arguments.get("limit", _DEFAULT_LIMIT))
    limit = max(1, min(limit, 100))

    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    sem_on, _ = workspace_retrieval_flags(context)
    if not sem_on:
        return json.dumps(
            {
                "ok": False,
                "skipped": True,
                "reason": "semantic_index_disabled",
                "results": [],
            },
            ensure_ascii=False,
        )
    workspace_id = str(ws.get("id") or "")

    try:
        code_index = get_code_index()
        results = code_index.search(
            query=str(query),
            workspace_id=workspace_id,
            limit=limit,
            kind=kind if kind else None,
        )
        return json.dumps(
            {
                "ok": True,
                "query": str(query),
                "kind": kind,
                "results": results,
                "count": len(results),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {"ok": False, "error": str(e)},
            ensure_ascii=False,
        )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "semantic_search": semantic_search,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Semantic search query (e.g., 'function that parses JSON')",
                    },
                    "kind": {
                        "type": "string",
                        "description": "Optional filter by symbol kind: function, class, import",
                    },
                    "limit": {
                        "type": "integer",
                        "description": f"Max results (default {_DEFAULT_LIMIT})",
                    },
                },
                "required": ["query"],
            },
        },
    },
]