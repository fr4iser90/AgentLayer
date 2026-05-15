"""Build/update the fast code index with tree-sitter symbol extraction + Qdrant storage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from plugins.tools.capabilities.coding.coding_index_lib import (
    _HAS_TS,
    _SUPPORTED_LANGUAGES,
    get_index,
)
from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

try:
    from apps.backend.infrastructure.code_index_qdrant import get_code_index
    _HAS_QDRANT = True
except ImportError:
    _HAS_QDRANT = False

__version__ = "1.0.0"
TOOL_ID = "coding_index"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding index", "index code", "build index", "scan project")
TOOL_CAPABILITIES = ("coding.index",)
TOOL_LABEL = "Coding: Index"
TOOL_DESCRIPTION = (
    "Build or refresh the code index for the coding workspace. "
    "Uses tree-sitter to parse symbols (functions, classes, imports) from source files. "
    f"Supported languages: {', '.join(sorted(set(_SUPPORTED_LANGUAGES.values())))}. "
    "Index enables fast symbol lookup, search, and code navigation. "
    "Symbols are also stored in Qdrant for semantic search."
)

_DEFAULT_MAX_FILES = 5000


def coding_index(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not _HAS_TS:
        return json.dumps(
            {
                "ok": False,
                "error": "tree-sitter not installed. Run: pip install tree-sitter tree-sitter-languages",
            },
            ensure_ascii=False,
        )
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    workspace_id = str(ws.get("id") or "")
    root = Path(ws["path"])
    max_files = int(arguments.get("max_files", _DEFAULT_MAX_FILES))
    max_files = max(100, min(max_files, 20000))

    idx = get_index()
    t0 = time.time()
    stats = idx.scan(root, max_files=max_files)
    elapsed = round(time.time() - t0, 2)

    qdrant_indexed = 0
    qdrant_error = None
    if _HAS_QDRANT:
        try:
            code_index = get_code_index()
            for file_entry in idx._files.values():
                if file_entry.symbols:
                    count = code_index.index_symbols(
                        [s.to_dict() for s in file_entry.symbols],
                        file_entry.path,
                        file_entry.language,
                        workspace_id,
                    )
                    qdrant_indexed += count
        except Exception as e:
            qdrant_error = str(e)

    result = {
        "ok": True,
        "stats": stats,
        "elapsed_sec": elapsed,
        "total_files": idx.file_count,
        "total_symbols": idx.symbol_count,
        "supported_languages": sorted(set(_SUPPORTED_LANGUAGES.values())),
    }
    if qdrant_indexed > 0:
        result["qdrant_indexed"] = qdrant_indexed
    if qdrant_error:
        result["qdrant_error"] = qdrant_error
    return json.dumps(result, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_index": coding_index,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_index",
            "TOOL_DESCRIPTION": "Build or refresh the code index for the coding workspace. "
            "Uses tree-sitter to parse symbols (functions, classes, imports) from source files. "
            f"Supported languages: {', '.join(sorted(set(_SUPPORTED_LANGUAGES.values())))}. "
            "Index enables fast symbol lookup, search, and code navigation. "
            "Symbols are also stored in Qdrant for semantic search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_files": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": f"Max files to index (default {_DEFAULT_MAX_FILES})",
                    },
                },
            },
        },
    },
]
