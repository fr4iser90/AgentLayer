"""Per-workspace semantic indexing and retrieval-layer settings."""

from __future__ import annotations

import json
import logging
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
        return {"configured": True, "reachable": bool(ok)}
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
) -> dict[str, Any]:
    """Tree-sitter scan + Qdrant upsert; updates ``last_index_*`` columns."""
    from plugins.tools.capabilities.coding.coding_index_lib import (
        _HAS_TS,
        get_index,
    )

    if not config.CODING_ENABLED:
        err = "coding tools disabled"
        _persist_index_result(workspace_id, stats={}, error=err)
        return {"ok": False, "error": err}

    if not _HAS_TS:
        err = "tree-sitter not installed"
        _persist_index_result(workspace_id, stats={}, error=err)
        return {"ok": False, "error": err}

    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        err = "workspace path not found"
        _persist_index_result(workspace_id, stats={}, error=err)
        return {"ok": False, "error": err}

    max_files = max(100, min(int(max_files), 20000))
    idx = get_index()
    t0 = time.time()
    scan_stats = idx.scan(root, max_files=max_files)
    elapsed = round(time.time() - t0, 2)

    qdrant_indexed = 0
    qdrant_error: str | None = None
    try:
        from apps.backend.infrastructure.code_index_qdrant import get_code_index

        code_index = get_code_index()
        for file_entry in idx._files.values():
            if file_entry.symbols:
                qdrant_indexed += code_index.index_symbols(
                    [s.to_dict() for s in file_entry.symbols],
                    file_entry.path,
                    file_entry.language,
                    workspace_id,
                )
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

    out: dict[str, Any] = {
        "ok": err is None or qdrant_indexed > 0,
        "stats": stats,
        "qdrant_indexed": qdrant_indexed,
    }
    if err:
        out["error"] = err
    return out
