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

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api

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


def _row_flags(row: tuple) -> tuple[bool, bool, bool]:
    sem = bool(row[13]) if row[13] is not None else True
    ret = bool(row[14]) if row[14] is not None else True
    docs = bool(row[18]) if len(row) > 18 and row[18] is not None else True
    return sem, ret, docs


def fetch_workspace_row(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
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
                "SELECT " + WORKSPACE_SELECT_SQL + """
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
        get_code_index = None  # codebase removed

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
    sem, ret, docs_rag = _row_flags(row)
    qd = qdrant_status()
    emb = embedding_status()
    stats = api.get("last_index_stats") if isinstance(api.get("last_index_stats"), dict) else {}
    stale_info: dict[str, Any] = {"stale": False, "reason": None}
    tree: list[str] = []
    try:
        from apps.backend.infrastructure.workspace.workspace_retrieval_bootstrap import (
            index_stale_reason,
            is_index_stale,
            list_repo_top_level,
        )

        stale_info["stale"] = bool(is_index_stale(api))
        stale_info["reason"] = index_stale_reason(api)
        p = api.get("path")
        if isinstance(p, str) and p.strip():
            tree = list_repo_top_level(Path(p))
    except Exception:
        pass
    index_on_write_effective = "debounced"
    files_stale = 0
    try:
        from apps.backend.infrastructure.workspace.workspace_index_file_state import count_files_out_of_date
        from apps.backend.infrastructure.workspace.workspace_index_policy import effective_index_on_write

        index_on_write_effective = effective_index_on_write(api)
        p = api.get("path")
        if isinstance(p, str) and p.strip() and api.get("id"):
            files_stale = count_files_out_of_date(str(api["id"]), Path(p))
    except Exception:
        pass

    return {
        "ok": True,
        "workspace_id": api["id"],
        "semantic_index_enabled": sem,
        "retrieval_enabled": ret,
        "docs_rag_enabled": docs_rag,
        "graph_index_enabled": api.get("graph_index_enabled", True),
        "index_on_write": api.get("index_on_write"),
        "index_on_write_effective": index_on_write_effective,
        "files_out_of_date": files_stale,
        "last_docs_rag_at": api.get("last_docs_rag_at"),
        "last_docs_rag_stats": api.get("last_docs_rag_stats"),
        "last_docs_rag_error": api.get("last_docs_rag_error"),
        "last_index_at": api.get("last_index_at"),
        "last_index_stats": stats,
        "last_index_error": api.get("last_index_error"),
        "index_stale": stale_info.get("stale"),
        "index_stale_reason": stale_info.get("reason"),
        "repo_tree": tree,
        "qdrant": qd,
        "neo4j": neo4j_status(),
        "embedding": emb,
        "coding_enabled": bool(config.CODING_ENABLED),
        "index_job": index_job_for_status(api["id"]),
    }


def neo4j_status() -> dict[str, Any]:
    try:
        _neo = None  # codebase removed

        return _neo()
    except Exception as e:
        return {"configured": False, "reachable": False, "error": str(e)[:200]}


from apps.backend.infrastructure.workspace.workspace_index_runner import (
    run_incremental_index,
    run_semantic_index,
    start_semantic_index_async,
)
