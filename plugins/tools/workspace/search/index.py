"""Build/update the fast code index with tree-sitter symbol extraction + Qdrant storage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.coding.index_lib import (
    _HAS_TS,
    _SUPPORTED_LANGUAGES,
    get_index,
)
from apps.backend.domain.coding.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
    workspace_retrieval_flags,
)

try:
    from apps.backend.infrastructure.code_index_qdrant import get_code_index
    _HAS_QDRANT = True
except ImportError:
    _HAS_QDRANT = False

try:
    from apps.backend.infrastructure.code_graph_neo4j import get_code_graph
    _HAS_NEO4J = True
except ImportError:
    _HAS_NEO4J = False

__version__ = "1.0.0"
TOOL_ID = "index"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "repository"
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


def index(arguments: dict[str, Any], context: dict | None = None) -> str:
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
    sem_on, _ = workspace_retrieval_flags(context)
    if not sem_on:
        return json.dumps(
            {
                "ok": False,
                "skipped": True,
                "reason": "semantic_index_disabled",
                "hint": "Enable indexing on this workspace in the Coding Agent header.",
            },
            ensure_ascii=False,
        )
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

    neo4j_edges = 0
    neo4j_error = None
    if _HAS_NEO4J:
        try:
            from apps.backend.domain.coding.graph_extract import resolve_import_relationships

            graph = get_code_graph()
            if graph.available():
                indexed_paths = set(idx._files.keys())
                for file_entry in idx._files.values():
                    import_rels = resolve_import_relationships(file_entry, indexed_paths)
                    all_rels = [r.to_dict() for r in file_entry.relationships] + import_rels
                    edges = graph.upsert_file_graph(
                        workspace_id=workspace_id,
                        file_path=file_entry.path,
                        language=file_entry.language,
                        sha256=file_entry.sha256,
                        symbols=[s.to_dict() for s in file_entry.symbols],
                        relationships=all_rels,
                    )
                    neo4j_edges += edges
        except Exception as e:
            neo4j_error = str(e)

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
    if neo4j_edges > 0:
        result["neo4j_edges"] = neo4j_edges
    if _HAS_QDRANT and qdrant_error is None:
        try:
            result.update(get_code_index().target_info())
        except Exception:
            pass
    if qdrant_error:
        result["qdrant_error"] = qdrant_error
    if neo4j_error:
        result["neo4j_error"] = neo4j_error
    if workspace_id:
        try:
            from apps.backend.infrastructure.workspace_retrieval import _persist_index_result

            stats_payload = {
                "scan": stats,
                "elapsed_sec": elapsed,
                "total_files": idx.file_count,
                "total_symbols": idx.symbol_count,
                "qdrant_indexed": qdrant_indexed,
                "neo4j_edges": neo4j_edges,
            }
            _persist_index_result(
                workspace_id,
                stats=stats_payload,
                error=qdrant_error,
            )
        except Exception:
            pass
    return json.dumps(result, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "index": index,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "index",
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
