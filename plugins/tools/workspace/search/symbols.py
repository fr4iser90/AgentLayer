"""Query symbols from the code index: lookup by name, search, list files."""

from __future__ import annotations

import json
from typing import Any, Callable

from apps.backend.core.config import config

from apps.backend.domain.coding.index_lib import (
    _HAS_TS,
    _SUPPORTED_LANGUAGES,
    get_index,
)

__version__ = "1.0.0"
TOOL_ID = "symbols"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "repository"
TOOL_TRIGGERS = ("coding symbols", "find symbol", "symbol lookup", "code index")
TOOL_CAPABILITIES = ("coding.index",)
TOOL_LABEL = "Coding: Symbols"
TOOL_DESCRIPTION = (
    "Query the code index for symbols. "
    "Operations: lookup (exact name), search (partial match), file (get file details), "
    "list (list all indexed files). "
    "Run coding_index first to build the index."
)

_VALID_OPS = {"lookup", "search", "file", "list"}


def symbols(arguments: dict[str, Any]) -> str:
    if not _HAS_TS:
        return json.dumps(
            {"ok": False, "error": "tree-sitter not installed"},
            ensure_ascii=False,
        )
    if not config.CODING_ENABLED:
        return json.dumps(
            {"ok": False, "error": "coding tools are disabled"},
            ensure_ascii=False,
        )
    op = (arguments.get("operation") or "").strip()
    if not op:
        idx = get_index()
        return json.dumps(
            {
                "ok": True,
                "operation": "status",
                "total_files": idx.file_count,
                "total_symbols": idx.symbol_count,
                "last_scan": idx.last_scan,
                "supported_languages": sorted(set(_SUPPORTED_LANGUAGES.values())),
                "operations": sorted(_VALID_OPS),
            },
            ensure_ascii=False,
        )
    if op not in _VALID_OPS:
        return json.dumps(
            {"ok": False, "error": f"operation must be one of {sorted(_VALID_OPS)}"},
            ensure_ascii=False,
        )
    idx = get_index()
    if op == "lookup":
        name = (arguments.get("name") or "").strip()
        if not name:
            return json.dumps({"ok": False, "error": "name is required for lookup"}, ensure_ascii=False)
        results = idx.lookup_symbol(name)
        return json.dumps(
            {"ok": True, "operation": "lookup", "name": name, "results": results, "count": len(results)},
            ensure_ascii=False,
        )
    if op == "search":
        query = (arguments.get("query") or "").strip()
        if not query:
            return json.dumps({"ok": False, "error": "query is required for search"}, ensure_ascii=False)
        kind = (arguments.get("kind") or "").strip() or None
        results = idx.search_symbols(query, kind=kind)
        return json.dumps(
            {"ok": True, "operation": "search", "query": query, "results": results, "count": len(results)},
            ensure_ascii=False,
        )
    if op == "file":
        path = (arguments.get("path") or "").strip()
        if not path:
            return json.dumps({"ok": False, "error": "path is required for file"}, ensure_ascii=False)
        result = idx.get_file(path)
        if result is None:
            return json.dumps(
                {"ok": False, "error": f"file {path!r} not in index. Run coding_index first."},
                ensure_ascii=False,
            )
        return json.dumps({"ok": True, "operation": "file", "file": result}, ensure_ascii=False)
    if op == "list":
        language = (arguments.get("language") or "").strip() or None
        results = idx.list_files(language=language)
        return json.dumps(
            {"ok": True, "operation": "list", "files": results, "count": len(results)},
            ensure_ascii=False,
        )
    return json.dumps({"ok": False, "error": "unreachable"}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "symbols": symbols,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "symbols",
            "TOOL_DESCRIPTION": "Query symbols from the code index: lookup by name, search, list files. "
            "Operations: lookup (exact name), search (partial match), file (get file details), "
            "list (list all indexed files). "
            "Run coding_index first to build the index.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "lookup (exact name), search (partial), file (details), list (all files)",
                    },
                    "name": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Exact symbol name for lookup",
                    },
                    "query": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Partial name for search",
                    },
                    "kind": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Filter by kind: function, class, import, namespace",
                    },
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path for file operation",
                    },
                    "language": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Filter list by language (python, typescript, etc.)",
                    },
                },
            },
        },
    },
]
