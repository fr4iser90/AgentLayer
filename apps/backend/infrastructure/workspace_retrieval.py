"""Per-workspace semantic indexing and retrieval-layer settings."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg.types.json import Json

from apps.backend.core.config import config
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api

logger = logging.getLogger(__name__)

_DEFAULT_MAX_FILES = 5000
_INDEX_JOBS_LOCK = threading.Lock()
_INDEX_JOBS: dict[str, dict[str, Any]] = {}


def _index_job_get(workspace_id: str) -> dict[str, Any] | None:
    with _INDEX_JOBS_LOCK:
        job = _INDEX_JOBS.get(workspace_id)
        return dict(job) if job else None


def _index_job_set(workspace_id: str, **fields: Any) -> dict[str, Any]:
    with _INDEX_JOBS_LOCK:
        job = _INDEX_JOBS.setdefault(workspace_id, {})
        job.update(fields)
        return dict(job)


def _index_job_clear(workspace_id: str) -> None:
    with _INDEX_JOBS_LOCK:
        _INDEX_JOBS.pop(workspace_id, None)


def index_job_for_status(workspace_id: str) -> dict[str, Any] | None:
    """Expose in-flight index progress for ``GET …/index/status``."""
    job = _index_job_get(workspace_id)
    if not job:
        return None
    status = str(job.get("status") or "")
    if status not in ("running", "done", "failed"):
        return None
    return {
        "status": status,
        "phase": job.get("phase"),
        "files_done": job.get("files_done"),
        "files_total": job.get("files_total"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "error": job.get("error"),
    }


def _row_flags(row: tuple) -> tuple[bool, bool]:
    sem = bool(row[13]) if row[13] is not None else True
    ret = bool(row[14]) if row[14] is not None else True
    return sem, ret


def fetch_workspace_row(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s
                """,
                (workspace_id, user_id),
            )
            return cur.fetchone()


def fetch_workspace_row_shared(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    """Owner, editor, or viewer may read settings."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {WORKSPACE_SELECT_SQL}
                FROM project_workspaces
                WHERE id = %s AND (owner_user_id = %s OR access_role IN ('editor', 'viewer'))
                """,
                (workspace_id, user_id),
            )
            return cur.fetchone()


def settings_from_workspace_dict(ws: dict[str, Any]) -> dict[str, bool]:
    return {
        "semantic_index_enabled": bool(ws.get("semantic_index_enabled", True)),
        "retrieval_enabled": bool(ws.get("retrieval_enabled", True)),
    }


def qdrant_status() -> dict[str, Any]:
    url = (config.QDRANT_URL or "").strip()
    if not url:
        return {"configured": False, "reachable": None}
    try:
        from apps.backend.infrastructure.code_index_qdrant import get_code_index

        idx = get_code_index()
        ok = idx.ensure_collection()
        out: dict[str, Any] = {"configured": True, "reachable": bool(ok)}
        out.update(idx.target_info())
        return out
    except Exception as e:
        return {"configured": True, "reachable": False, "error": str(e)[:200]}


def embedding_status() -> dict[str, Any]:
    rs = operator_settings.rag_settings()
    return {
        "configured": bool((rs.get("embedding_model") or "").strip()),
        "enabled": bool(rs.get("enabled", True)),
        "embedding_dim": rs.get("embedding_dim"),
    }


def index_status_payload(row: tuple | None) -> dict[str, Any]:
    if row is None:
        return {"ok": False, "error": "workspace not found"}
    api = workspace_row_to_api(row)
    sem, ret = _row_flags(row)
    qd = qdrant_status()
    emb = embedding_status()
    stats = api.get("last_index_stats") if isinstance(api.get("last_index_stats"), dict) else {}
    return {
        "ok": True,
        "workspace_id": api["id"],
        "semantic_index_enabled": sem,
        "retrieval_enabled": ret,
        "last_index_at": api.get("last_index_at"),
        "last_index_stats": stats,
        "last_index_error": api.get("last_index_error"),
        "qdrant": qd,
        "embedding": emb,
        "coding_enabled": bool(config.CODING_ENABLED),
        "index_job": index_job_for_status(api["id"]),
    }


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


def run_semantic_index(
    workspace_id: str,
    root_path: str | Path,
    *,
    max_files: int = _DEFAULT_MAX_FILES,
    track_progress: bool = False,
) -> dict[str, Any]:
    """Tree-sitter scan + Qdrant upsert; updates ``last_index_*`` columns."""
    from plugins.tools.capabilities.coding.coding_index_lib import (
        _HAS_TS,
        get_index,
    )

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
        from apps.backend.infrastructure.code_index_qdrant import get_code_index

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

    stats = {
        "scan": scan_stats,
        "elapsed_sec": elapsed,
        "total_files": idx.file_count,
        "total_symbols": idx.symbol_count,
        "qdrant_indexed": qdrant_indexed,
    }
    err = qdrant_error
    if qdrant_indexed == 0 and not qdrant_error:
        qd = qdrant_status()
        if not qd.get("reachable"):
            err = "Qdrant unreachable or embedding failed — check QDRANT_URL and EMBEDDING_*"

    _persist_index_result(workspace_id, stats=stats, error=err)

    ok = err is None or qdrant_indexed > 0
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
    }
    if err:
        out["error"] = err
    return out


def _run_index_job(workspace_id: str, root_path: str | Path, max_files: int) -> None:
    try:
        run_semantic_index(
            workspace_id,
            root_path,
            max_files=max_files,
            track_progress=True,
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
        args=(workspace_id, root_path, max_files),
        name=f"ws-index-{workspace_id[:8]}",
        daemon=True,
    )
    thread.start()
    return {
        "ok": True,
        "started": True,
        "job": index_job_for_status(workspace_id),
    }
