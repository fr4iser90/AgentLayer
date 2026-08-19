"""Workspace semantic index execution and result persistence."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace.workspace_retrieval import _index_job_clear, _index_job_set, _row_flags

logger = logging.getLogger(__name__)
_DEFAULT_MAX_FILES = 5000

def _persist_docs_rag_result(
    workspace_id: str,
    *,
    stats: dict[str, Any],
    error: str | None,
) -> None:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_workspaces
                SET last_docs_rag_at = %s,
                    last_docs_rag_stats = %s,
                    last_docs_rag_error = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (now, Json(stats), error, workspace_id),
            )
        conn.commit()


def _workspace_graph_index_enabled(workspace_id: str) -> bool:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT graph_index_enabled FROM project_workspaces WHERE id = %s",
                    (workspace_id,),
                )
                row = cur.fetchone()
        if not row:
            return True
        return bool(row[0]) if row[0] is not None else True
    except Exception:
        return True


def _persist_index_result(
    workspace_id: str,
    *,
    stats: dict[str, Any],
    error: str | None,
) -> None:
    now = datetime.now(UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE project_workspaces
                SET last_index_at = %s,
                    last_index_stats = %s,
                    last_index_error = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (now, Json(stats), error, workspace_id),
            )
        conn.commit()


def _run_docs_rag_phase(
    workspace_id: str,
    root: Path,
    *,
    track_progress: bool,
    docs_on: bool,
) -> tuple[dict[str, Any] | None, str | None]:
    """Ingest workspace ``*.md`` into pgvector when enabled."""
    if not docs_on:
        return None, None
    if not operator_settings.rag_settings()["enabled"]:
        return None, "RAG disabled (operator settings)"

    if track_progress:
        _index_job_set(workspace_id, phase="docs_rag", files_done=0, files_total=1)

    try:
        from apps.backend.infrastructure.workspace.workspace_rag_ingest_service import ingest_workspace_markdown_tree

        summary = ingest_workspace_markdown_tree(
            uuid.UUID(workspace_id),
            root,
            purge_first=True,
        )
    except Exception as e:
        logger.warning("workspace docs rag: %s", e)
        if track_progress:
            _index_job_set(workspace_id, phase="docs_rag", files_done=1, files_total=1)
        return None, str(e)[:500]

    docs_error: str | None = None
    if not summary.get("ok"):
        errs = summary.get("errors")
        if isinstance(errs, list) and errs:
            docs_error = str(errs[0].get("error", errs[0]))[:500]
        else:
            docs_error = str(summary.get("error") or "docs RAG ingest failed")[:500]

    if track_progress:
        _index_job_set(workspace_id, phase="docs_rag", files_done=1, files_total=1)

    docs_stats = {
        "files_ingested": summary.get("files_ingested"),
        "chunk_count_total": summary.get("chunk_count_total"),
        "purge_deleted_documents": summary.get("purge_deleted_documents"),
    }
    return docs_stats, docs_error


def run_incremental_index(
    workspace_id: str,
    root_path: str | Path,
    rel_paths: list[str],
    *,
    semantic_index_enabled: bool = True,
) -> dict[str, Any]:
    """Re-index only touched files into Qdrant + Neo4j (post-write background job)."""
    if not semantic_index_enabled:
        return {"ok": False, "skipped": True, "reason": "semantic_index_disabled"}
    if not config.CODING_ENABLED:
        return {"ok": False, "error": "coding tools disabled"}

    _HAS_TS = False; get_index = None  # codebase removed

    if not _HAS_TS:
        return {"ok": False, "error": "tree-sitter not installed"}

    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        return {"ok": False, "error": "workspace path not found"}

    normalized: list[str] = []
    seen: set[str] = set()
    for p in rel_paths:
        rel = (p or "").strip().replace("\\", "/").lstrip("/")
        if rel and rel not in seen:
            seen.add(rel)
            normalized.append(rel)
    if not normalized:
        return {"ok": True, "skipped": True, "reason": "no_paths"}

    job = _index_job_get(workspace_id)
    if job and str(job.get("status")) == "running" and str(job.get("phase") or "") != "incremental":
        return {"ok": False, "skipped": True, "reason": "full_index_running"}

    started = datetime.now(UTC).isoformat()
    _index_job_set(
        workspace_id,
        status="running",
        phase="incremental",
        files_done=0,
        files_total=len(normalized),
        started_at=started,
        finished_at=None,
        error=None,
    )

    idx = get_index()
    indexed_paths = idx.list_indexable_rel_paths(root)
    file_entries, scan_stats = idx.scan_paths(root, normalized)

    qdrant_indexed = 0
    qdrant_error: str | None = None
    neo4j_edges = 0
    neo4j_error: str | None = None
    removed = 0

    try:
        get_code_index = None  # codebase removed

        code_index = get_code_index()
        for rel in normalized:
            fp = root / rel
            if not fp.is_file():
                code_index.delete_file_symbols(workspace_id, rel)
                removed += 1
        for i, file_entry in enumerate(file_entries):
            qdrant_indexed += code_index.index_symbols(
                [s.to_dict() for s in file_entry.symbols],
                file_entry.path,
                file_entry.language,
                workspace_id,
            )
            _index_job_set(workspace_id, phase="incremental", files_done=i + 1, files_total=len(normalized))
    except Exception as e:
        qdrant_error = str(e)[:500]
        logger.warning("incremental index qdrant: %s", e)

    graph_on = _workspace_graph_index_enabled(workspace_id)

    try:
        get_code_graph = None  # codebase removed
        resolve_import_relationships = None  # codebase removed

        graph = get_code_graph()
        if graph.available() and graph_on:
            for rel in normalized:
                if not (root / rel).is_file():
                    graph.delete_file_graph(workspace_id, rel)
            for file_entry in file_entries:
                import_rels = resolve_import_relationships(file_entry, indexed_paths)
                all_rels = [r.to_dict() for r in file_entry.relationships] + import_rels
                neo4j_edges += graph.upsert_file_graph(
                    workspace_id=workspace_id,
                    file_path=file_entry.path,
                    language=file_entry.language,
                    sha256=file_entry.sha256,
                    symbols=[s.to_dict() for s in file_entry.symbols],
                    relationships=all_rels,
                )
    except Exception as e:
        neo4j_error = str(e)[:500]
        logger.warning("incremental index neo4j: %s", e)

    stats: dict[str, Any] = {
        "incremental": True,
        "paths": normalized,
        "scan": scan_stats,
        "removed_paths": removed,
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
    }
    err = qdrant_error or neo4j_error
    ok = err is None or qdrant_indexed > 0 or neo4j_edges > 0 or removed > 0

    try:
        from apps.backend.infrastructure.workspace.workspace_index_file_state import upsert_file_states

        upsert_file_states(
            workspace_id,
            [(fe.path, fe.sha256) for fe in file_entries if fe.sha256],
        )
        for rel in normalized:
            if not (root / rel).is_file():
                from apps.backend.infrastructure.workspace.workspace_index_file_state import delete_file_state

                delete_file_state(workspace_id, rel)
    except Exception as e:
        logger.debug("incremental file state update: %s", e)

    _persist_index_result(workspace_id, stats=stats, error=err if not ok else None)
    finished = datetime.now(UTC).isoformat()
    _index_job_set(
        workspace_id,
        status="done" if ok else "failed",
        phase="incremental",
        files_done=len(normalized),
        files_total=len(normalized),
        finished_at=finished,
        error=err if not ok else None,
    )
    logger.info(
        "incremental index workspace=%s paths=%d qdrant=%d neo4j_edges=%d removed=%d",
        workspace_id,
        len(normalized),
        qdrant_indexed,
        neo4j_edges,
        removed,
    )
    return {
        "ok": ok,
        "stats": stats,
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
        "error": err,
    }


def run_semantic_index(
    workspace_id: str,
    root_path: str | Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    track_progress: bool = False,
    mode: str = "full",
) -> dict[str, Any]:
    """Tree-sitter scan + Qdrant + Neo4j graph + optional workspace docs RAG."""
    mode = (mode or "full").strip().lower()
    if mode not in ("full", "code", "docs"):
        mode = "full"

    if mode == "docs":
        root = Path(root_path)
        if not root.exists() or not root.is_dir():
            err = "workspace path not found"
            _persist_docs_rag_result(workspace_id, stats={}, error=err)
            if track_progress:
                _index_job_set(
                    workspace_id,
                    status="failed",
                    phase="failed",
                    error=err,
                    finished_at=datetime.now(UTC).isoformat(),
                )
            return {"ok": False, "error": err}
        docs_stats, docs_error = _run_docs_rag_phase(
            workspace_id, root, track_progress=track_progress, docs_on=True
        )
        stats: dict[str, Any] = {}
        if docs_stats:
            stats["docs_rag"] = docs_stats
        _persist_docs_rag_result(workspace_id, stats=docs_stats or {}, error=docs_error)
        ok = docs_error is None
        if track_progress:
            finished = datetime.now(UTC).isoformat()
            _index_job_set(
                workspace_id,
                status="done" if ok else "failed",
                phase="done" if ok else "failed",
                finished_at=finished,
                error=docs_error,
            )
        return {"ok": ok, "stats": stats, "docs_rag": docs_stats}
    _HAS_TS = False
    get_index = None  # codebase removed

    def _progress(**fields: Any) -> None:
        if track_progress:
            _index_job_set(workspace_id, **fields)

    if not config.CODING_ENABLED:
        err = "coding tools disabled"
        _persist_index_result(workspace_id, stats={}, error=err)
        if track_progress:
            _index_job_set(
                workspace_id,
                status="failed",
                phase="failed",
                error=err,
                finished_at=datetime.now(UTC).isoformat(),
            )
        return {"ok": False, "error": err}

    if not _HAS_TS:
        err = "tree-sitter not installed"
        _persist_index_result(workspace_id, stats={}, error=err)
        if track_progress:
            _index_job_set(
                workspace_id,
                status="failed",
                phase="failed",
                error=err,
                finished_at=datetime.now(UTC).isoformat(),
            )
        return {"ok": False, "error": err}

    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        err = "workspace path not found"
        _persist_index_result(workspace_id, stats={}, error=err)
        if track_progress:
            _index_job_set(
                workspace_id,
                status="failed",
                phase="failed",
                error=err,
                finished_at=datetime.now(UTC).isoformat(),
            )
        return {"ok": False, "error": err}

    max_files = max(100, min(int(max_files), 20000))
    idx = get_index()
    t0 = time.time()
    if track_progress:
        _progress(status="running", phase="scan", files_done=0, files_total=0)

    def on_scan_progress(done: int, total: int) -> None:
        _progress(phase="scan", files_done=done, files_total=total)

    scan_stats = idx.scan(root, max_files=max_files, on_progress=on_scan_progress if track_progress else None)
    elapsed = round(time.time() - t0, 2)

    qdrant_indexed = 0
    qdrant_error: str | None = None
    try:
        get_code_index = None  # codebase removed

        code_index = get_code_index()
        files_with_syms = [f for f in idx._files.values() if f.symbols]
        qdrant_total = len(files_with_syms)
        if track_progress:
            _progress(phase="qdrant", files_done=0, files_total=qdrant_total)
        for i, file_entry in enumerate(files_with_syms):
            qdrant_indexed += code_index.index_symbols(
                [s.to_dict() for s in file_entry.symbols],
                file_entry.path,
                file_entry.language,
                workspace_id,
            )
            if track_progress and (i % 2 == 0 or i + 1 == qdrant_total):
                _progress(phase="qdrant", files_done=i + 1, files_total=qdrant_total)
    except Exception as e:
        qdrant_error = str(e)[:500]
        logger.warning("workspace index qdrant: %s", e)

    neo4j_edges = 0
    neo4j_error: str | None = None
    try:
        get_code_graph = None  # codebase removed

        graph = get_code_graph()
        if graph.available() and _workspace_graph_index_enabled(workspace_id):
            file_list = list(idx._files.values())
            neo4j_total = len(file_list)

            def on_neo4j_progress(done: int, total: int) -> None:
                _progress(phase="neo4j", files_done=done, files_total=total)

            if track_progress:
                _progress(phase="neo4j", files_done=0, files_total=neo4j_total)
            neo4j_edges, neo4j_error = graph.upsert_workspace_files(
                workspace_id,
                file_list,
                on_progress=on_neo4j_progress if track_progress else None,
            )
    except Exception as e:
        neo4j_error = str(e)[:500]
        logger.warning("workspace index neo4j: %s", e)

    try:
        from apps.backend.infrastructure.workspace.workspace_index_file_state import upsert_file_states

        upsert_file_states(
            workspace_id,
            [(fe.path, fe.sha256) for fe in idx._files.values() if fe.sha256],
        )
    except Exception as e:
        logger.debug("full index file state: %s", e)

    stats = {
        "scan": scan_stats,
        "elapsed_sec": elapsed,
        "total_files": idx.file_count,
        "total_symbols": idx.symbol_count,
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
    }
    err = qdrant_error or neo4j_error
    if qdrant_indexed == 0 and not qdrant_error:
        qd = qdrant_status()
        if not qd.get("reachable"):
            err = "Qdrant unreachable or embedding failed — check QDRANT_URL and EMBEDDING_*"

    docs_rag_error: str | None = None
    docs_on = True
    if mode == "full":
        try:
            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT docs_rag_enabled FROM project_workspaces WHERE id = %s",
                        (workspace_id,),
                    )
                    dr = cur.fetchone()
            docs_on = bool(dr[0]) if dr and dr[0] is not None else True
        except Exception:
            docs_on = True
        docs_stats, docs_rag_error = _run_docs_rag_phase(
            workspace_id, root, track_progress=track_progress, docs_on=docs_on
        )
        if docs_stats:
            stats["docs_rag"] = docs_stats

    _persist_index_result(workspace_id, stats=stats, error=err)
    if mode == "full":
        _persist_docs_rag_result(
            workspace_id,
            stats=stats.get("docs_rag") or {},
            error=docs_rag_error,
        )

    code_ok = err is None or qdrant_indexed > 0 or neo4j_edges > 0
    docs_ok = mode != "full" or (
        not docs_on
        or docs_rag_error is None
        or bool(stats.get("docs_rag", {}).get("files_ingested"))
    )
    ok = code_ok and docs_ok
    if track_progress:
        finished = datetime.now(UTC).isoformat()
        if ok:
            _index_job_set(
                workspace_id,
                status="done",
                phase="done",
                files_done=stats.get("total_files"),
                files_total=stats.get("total_files"),
                finished_at=finished,
                error=None,
            )
        else:
            _index_job_set(
                workspace_id,
                status="failed",
                phase="failed",
                finished_at=finished,
                error=err or "index failed",
            )

    out: dict[str, Any] = {
        "ok": ok,
        "stats": stats,
        "qdrant_indexed": qdrant_indexed,
        "neo4j_edges": neo4j_edges,
    }
    if err:
        out["error"] = err
    if neo4j_error:
        out["neo4j_error"] = neo4j_error
    return out


def _run_index_job(workspace_id: str, root_path: str | Path, max_files: int, mode: str = "full") -> None:
    try:
        run_semantic_index(
            workspace_id,
            root_path,
            max_files=max_files,
            track_progress=True,
            mode=mode,
        )
    except Exception as e:
        logger.exception("workspace index job %s", workspace_id)
        _index_job_set(
            workspace_id,
            status="failed",
            phase="failed",
            error=str(e)[:500],
            finished_at=datetime.now(UTC).isoformat(),
        )
        _persist_index_result(workspace_id, stats={}, error=str(e)[:500])


def start_semantic_index_async(
    workspace_id: str,
    root_path: str | Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    mode: str = "full",
) -> dict[str, Any]:
    """Start background index; returns immediately with job snapshot."""
    existing = _index_job_get(workspace_id)
    if existing and existing.get("status") == "running":
        return {"ok": True, "already_running": True, "job": index_job_for_status(workspace_id)}

    started_at = datetime.now(UTC).isoformat()
    _index_job_set(
        workspace_id,
        status="running",
        phase="starting",
        files_done=0,
        files_total=0,
        started_at=started_at,
        finished_at=None,
        error=None,
    )
    thread = threading.Thread(
        target=_run_index_job,
        args=(workspace_id, root_path, max_files, mode),
        name=f"ws-index-{workspace_id[:8]}",
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "started": True,
        "job": index_job_for_status(workspace_id),
    }
