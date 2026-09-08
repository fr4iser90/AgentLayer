"""Ingest client-uploaded symbol tables and markdown (ADR 0009 M3/M4).

The backend must never open ``project_workspaces.path`` for a client row. Callers pass already
sanitized relative paths and file bodies; this module writes Qdrant / Neo4j / pgvector only.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from apps.backend.infrastructure.workspace.workspace_index_consent import sanitize_upload_rel_path

logger = logging.getLogger(__name__)

_MAX_FILES = 5000
_MAX_SYMBOLS_PER_FILE = 200
_MAX_NAME = 256
_MAX_SIGNATURE = 200
_MAX_LANGUAGE = 32
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_VALID_KINDS = frozenset({"function", "class", "import", "namespace", "method", "type", "unknown"})


def sanitize_symbol_files(
    files: list[Any],
    *,
    max_files: int = _MAX_FILES,
    max_symbols_per_file: int = _MAX_SYMBOLS_PER_FILE,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return ``(clean_files, errors)``. Does not touch disk or the index stores."""
    errors: list[str] = []
    if not isinstance(files, list):
        return [], ["files must be a JSON array"]
    if len(files) > max_files:
        errors.append(f"at most {max_files} files per upload")
        files = files[:max_files]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(files):
        if not isinstance(raw, dict):
            errors.append(f"files[{i}] must be an object")
            continue
        path = sanitize_upload_rel_path(raw.get("path"))
        if not path:
            errors.append(f"files[{i}].path must be a relative path inside the workspace")
            continue
        if path in seen:
            errors.append(f"duplicate path {path}")
            continue
        seen.add(path)
        sha = str(raw.get("sha256") or "").strip().lower()
        if not _SHA256_RE.match(sha):
            errors.append(f"{path}: sha256 must be 64 lowercase hex characters")
            continue
        language = str(raw.get("language") or "").strip()[:_MAX_LANGUAGE]
        raw_syms = raw.get("symbols")
        if raw_syms is None:
            raw_syms = []
        if not isinstance(raw_syms, list):
            errors.append(f"{path}: symbols must be an array")
            continue
        if len(raw_syms) > max_symbols_per_file:
            errors.append(f"{path}: truncated to {max_symbols_per_file} symbols")
            raw_syms = raw_syms[:max_symbols_per_file]
        symbols: list[dict[str, Any]] = []
        for j, sym in enumerate(raw_syms):
            if not isinstance(sym, dict):
                errors.append(f"{path}: symbols[{j}] must be an object")
                continue
            name = str(sym.get("name") or "").strip()[:_MAX_NAME]
            if not name:
                continue
            kind = str(sym.get("kind") or "unknown").strip().lower()
            if kind not in _VALID_KINDS:
                kind = "unknown"
            sig = str(sym.get("signature") or "")[:_MAX_SIGNATURE]
            symbols.append(
                {
                    "kind": kind,
                    "name": name,
                    "line": _int(sym.get("line"), 0),
                    "col": _int(sym.get("col"), 0),
                    "end_line": _int(sym.get("end_line"), 0),
                    "end_col": _int(sym.get("end_col"), 0),
                    "signature": sig,
                }
            )
        out.append({"path": path, "sha256": sha, "language": language, "symbols": symbols})
    return out, errors


def sanitize_text_documents(
    documents: list[Any],
    *,
    max_files: int = 500,
    max_bytes: int = 2_000_000,
) -> tuple[list[tuple[str, str]], list[str]]:
    errors: list[str] = []
    if not isinstance(documents, list):
        return [], ["documents must be a JSON array"]
    if len(documents) > max_files:
        errors.append(f"at most {max_files} documents per upload")
        documents = documents[:max_files]
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, raw in enumerate(documents):
        if not isinstance(raw, dict):
            errors.append(f"documents[{i}] must be an object")
            continue
        path = sanitize_upload_rel_path(raw.get("path"))
        if not path:
            errors.append(f"documents[{i}].path must be a relative path inside the workspace")
            continue
        if path in seen:
            errors.append(f"duplicate path {path}")
            continue
        seen.add(path)
        text = raw.get("text")
        if not isinstance(text, str):
            errors.append(f"{path}: text must be a string")
            continue
        if len(text.encode("utf-8", errors="replace")) > max_bytes:
            errors.append(f"{path}: file too large (>{max_bytes} bytes)")
            continue
        stripped = text.strip()
        if not stripped:
            continue
        out.append((path, stripped))
    return out, errors


def ingest_client_symbols(
    workspace_id: str,
    files: list[dict[str, Any]],
    *,
    replace_all: bool = True,
) -> dict[str, Any]:
    """Upsert sanitized symbol files into Qdrant + Neo4j. Does not open the workspace path."""
    clean, errors = sanitize_symbol_files(files)
    qdrant_indexed = 0
    neo4j_edges = 0
    qdrant_error: str | None = None
    neo4j_error: str | None = None

    try:
        from apps.backend.infrastructure.codebase.code_index_qdrant import get_code_index

        code_index = get_code_index()
        if replace_all:
            code_index.delete_workspace(workspace_id)
        for entry in clean:
            qdrant_indexed += code_index.index_symbols(
                entry["symbols"],
                entry["path"],
                entry["language"],
                workspace_id,
            )
    except Exception as exc:
        qdrant_error = str(exc)[:500]
        logger.warning("client symbol ingest qdrant: %s", exc)

    try:
        from apps.backend.infrastructure.codebase.code_graph_neo4j import get_code_graph

        graph = get_code_graph()
        if graph.available():
            if replace_all:
                graph.delete_workspace(workspace_id)
            for entry in clean:
                neo4j_edges += graph.upsert_file_graph(
                    workspace_id=workspace_id,
                    file_path=entry["path"],
                    language=entry["language"],
                    sha256=entry["sha256"],
                    symbols=entry["symbols"],
                    relationships=[],
                )
    except Exception as exc:
        neo4j_error = str(exc)[:500]
        logger.warning("client symbol ingest neo4j: %s", exc)

    try:
        from apps.backend.infrastructure.workspace.workspace_index_file_state import upsert_file_states

        upsert_file_states(workspace_id, [(e["path"], e["sha256"]) for e in clean if e["sha256"]])
    except Exception as exc:
        logger.debug("client symbol file state: %s", exc)

    err = qdrant_error or neo4j_error
    stats: dict[str, Any] = {
        "source": "client_upload",
        "files": len(clean),
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
        "replace_all": bool(replace_all),
        "sanitize_errors": errors[:50],
    }
    try:
        from apps.backend.infrastructure.workspace.workspace_index_runner import _persist_index_result

        _persist_index_result(workspace_id, stats=stats, error=err)
    except Exception as exc:
        logger.warning("client symbol persist: %s", exc)

    return {
        "ok": err is None,
        "workspace_id": workspace_id,
        "files": len(clean),
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
        "errors": errors,
        "store_error": err,
        "stats": stats,
    }


def ingest_client_text(
    workspace_id: str,
    documents: list[dict[str, Any]],
    *,
    purge_first: bool = True,
) -> dict[str, Any]:
    clean, errors = sanitize_text_documents(documents)
    try:
        wid = uuid.UUID(str(workspace_id))
    except ValueError:
        return {"ok": False, "error": "invalid workspace id", "errors": errors}

    from apps.backend.domain.rag.workspace_ingest import ingest_workspace_markdown_documents

    summary = ingest_workspace_markdown_documents(
        wid,
        clean,
        purge_first=purge_first,
    )
    docs_error: str | None = None
    if not summary.get("ok"):
        errs = summary.get("errors")
        if isinstance(errs, list) and errs:
            first = errs[0]
            docs_error = str(first.get("error", first) if isinstance(first, dict) else first)[:500]
        else:
            docs_error = str(summary.get("error") or "docs RAG ingest failed")[:500]
    stats = {
        "source": "client_upload",
        "files_ingested": summary.get("files_ingested"),
        "chunk_count_total": summary.get("chunk_count_total"),
        "purge_deleted_documents": summary.get("purge_deleted_documents"),
        "sanitize_errors": errors[:50],
    }
    try:
        from apps.backend.infrastructure.workspace.workspace_index_runner import _persist_docs_rag_result

        _persist_docs_rag_result(workspace_id, stats=stats, error=docs_error)
    except Exception as exc:
        logger.warning("client text persist: %s", exc)
    return {
        "ok": bool(summary.get("ok")) and docs_error is None,
        "workspace_id": workspace_id,
        "files_ingested": summary.get("files_ingested"),
        "chunk_count_total": summary.get("chunk_count_total"),
        "errors": errors + list(summary.get("errors") or []),
        "store_error": docs_error,
        "stats": stats,
    }


def _int(raw: Any, default: int) -> int:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return default
    return max(0, min(n, 10_000_000))
