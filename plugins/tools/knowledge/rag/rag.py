"""Vector RAG over Postgres + pgvector (configurable embeddings). Scoped per user like KB/todos."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.rag.rag import rag as rag_service

try:
    from plugins.tools.knowledge.lib.common import (
        workspace_docs_rag_enabled,
        workspace_id_from_context,
    )
except ImportError:
    workspace_id_from_context = None  # type: ignore[misc, assignment]
    workspace_docs_rag_enabled = None  # type: ignore[misc, assignment]

__version__ = "1.0.0"
TOOL_ID = "rag"
TOOL_BUCKET = "knowledge"
TOOL_DOMAIN = "rag"
TOOL_LABEL = "RAG"
TOOL_DESCRIPTION = (
    "Semantic search over ingested documents (pgvector + configurable embeddings)."
)
# Router phrases: co-located rag.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("knowledge.retrieve",)


def rag_search(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not operator_settings.rag_settings()["enabled"]:
        return json.dumps({"ok": False, "error": "RAG disabled (operator settings)"})
    q = (arguments.get("query") or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "query is required"})
    top_k = int(operator_settings.rag_settings()["top_k"])
    try:
        limit = int(arguments.get("limit") or top_k)
    except (TypeError, ValueError):
        limit = top_k

    wid_raw = workspace_id_from_context(context) if workspace_id_from_context else None
    if wid_raw:
        if workspace_docs_rag_enabled is not None and not workspace_docs_rag_enabled(context):
            return json.dumps(
                {"ok": False, "skipped": True, "reason": "docs_rag_disabled"},
                ensure_ascii=False,
            )
        try:
            rows = rag_service.search_for_identity(
                q, limit=limit, workspace_id=uuid.UUID(wid_raw)
            )
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
        return json.dumps(
            {
                "ok": True,
                "scope": "workspace",
                "workspace_id": wid_raw,
                "hits": rows,
                "count": len(rows),
            },
            ensure_ascii=False,
        )

    domain = arguments.get("domain")
    dom = domain.strip() if isinstance(domain, str) else None
    if dom == "":
        dom = None
    try:
        rows = rag_service.search_for_identity(q, domain=dom, limit=limit)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps(
        {"ok": True, "scope": "global", "hits": rows, "count": len(rows)},
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "rag_search": rag_search,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "TOOL_DESCRIPTION": (
                "Semantic search over ingested documents (vector similarity). "
                "With an active coding workspace: searches only that workspace's indexed *.md (run Reindex). "
                "Without a workspace: pass domain=\"agentlayer_docs\" for product docs, or omit for personal RAG. "
                "Admin ingest: POST /v1/admin/rag/ingest or ingest-docs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Natural-language query to embed and match.",
                    },
                    "domain": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Optional domain filter. Use agentlayer_docs for product docs (shared in tenant). "
                            "Omit to search the caller's personal RAG across all their domains."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Max hits 1–50 (default from operator rag_top_k).",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
