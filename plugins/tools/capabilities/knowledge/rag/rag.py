"""Vector RAG over Postgres + pgvector (Ollama embeddings). Scoped per user like KB/todos."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.rag import rag as rag_service

__version__ = "1.0.0"
TOOL_ID = "rag"
TOOL_BUCKET = "knowledge"
TOOL_DOMAIN = "rag"
TOOL_LABEL = "RAG"
TOOL_DESCRIPTION = (
    "Semantic search over ingested documents (pgvector + Ollama embeddings)."
)
TOOL_TRIGGERS = (
    "rag",
    "vector search",
    "semantic search",
    "embeddings",
    "knowledge base documents",
)
TOOL_CAPABILITIES = ("knowledge.retrieve",)


def rag_search(arguments: dict[str, Any]) -> str:
    if not operator_settings.rag_settings()["enabled"]:
        return json.dumps({"ok": False, "error": "RAG disabled (operator settings)"})
    q = (arguments.get("query") or "").strip()
    if not q:
        return json.dumps({"ok": False, "error": "query is required"})
    domain = arguments.get("domain")
    dom = domain.strip() if isinstance(domain, str) else None
    if dom == "":
        dom = None
    top_k = int(operator_settings.rag_settings()["top_k"])
    try:
        limit = int(arguments.get("limit") or top_k)
    except (TypeError, ValueError):
        limit = top_k
    try:
        rows = rag_service.search_for_identity(q, domain=dom, limit=limit)
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps(
        {"ok": True, "hits": rows, "count": len(rows)},
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
                "Pass domain=\"agentlayer_docs\" for official AgentLayer markdown (tenant-wide after admin ingest-docs). "
                "Other domains are per-user. Ingest: POST /v1/admin/rag/ingest or /v1/admin/rag/ingest-docs (admin only)."
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
