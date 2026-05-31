"""Debounced incremental workspace index after coding tool writes (Qdrant + Neo4j)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from apps.backend.core.config import config

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_PENDING: dict[str, dict[str, Any]] = {}


def _debounce_seconds() -> float:
    if config.AGENT_WORKSPACE_INDEX_ON_WRITE == "immediate":
        return 0.0
    return float(config.AGENT_WORKSPACE_INDEX_DEBOUNCE_SEC)


def _full_index_running(workspace_id: str) -> bool:
    try:
        from apps.backend.infrastructure.workspace_retrieval import index_job_for_status

        job = index_job_for_status(workspace_id)
        if not job:
            return False
        return str(job.get("status")) == "running" and str(job.get("phase") or "") != "incremental"
    except Exception:
        return False


def enqueue_incremental_index(
    workspace_id: str,
    root_path: str,
    rel_paths: list[str],
    *,
    semantic_index_enabled: bool = True,
    workspace: dict[str, Any] | None = None,
) -> None:
    """Queue workspace-relative paths for a background incremental index."""
    from apps.backend.infrastructure.workspace_index_policy import effective_index_on_write

    mode = effective_index_on_write(workspace)
    if mode == "off":
        return
    if not config.CODING_ENABLED:
        return
    if not semantic_index_enabled:
        return
    wid = (workspace_id or "").strip()
    root = (root_path or "").strip()
    if not wid or not root:
        return
    if _full_index_running(wid):
        logger.debug("incremental index skipped: full index running for %s", wid)
        return

    normalized: list[str] = []
    for p in rel_paths:
        rel = (p or "").strip().replace("\\", "/").lstrip("/")
        if rel and rel not in normalized:
            normalized.append(rel)
    if not normalized:
        return

    if mode == "immediate":
        delay = 0.0
    else:
        delay = _debounce_seconds()
    with _LOCK:
        entry = _PENDING.setdefault(
            wid,
            {"root": root, "paths": set(), "timer": None, "semantic_index_enabled": semantic_index_enabled},
        )
        entry["root"] = root
        entry["semantic_index_enabled"] = semantic_index_enabled
        entry["paths"].update(normalized)
        old_timer = entry.get("timer")
        if old_timer is not None:
            try:
                old_timer.cancel()
            except Exception:
                pass
        if delay <= 0:
            entry["timer"] = None
            paths_snapshot = list(entry["paths"])
            root_snapshot = entry["root"]
            sem = entry["semantic_index_enabled"]
            _PENDING.pop(wid, None)
        else:
            timer = threading.Timer(delay, _flush_workspace, args=(wid,))
            timer.daemon = True
            entry["timer"] = timer
            timer.start()
            return

    threading.Thread(
        target=_run_incremental_job,
        args=(wid, root_snapshot, paths_snapshot, sem),
        daemon=True,
        name=f"incr-index-{wid[:8]}",
    ).start()


def enqueue_incremental_index_from_context(
    context: dict[str, Any] | None,
    rel_paths: list[str],
) -> None:
    """Enqueue paths using workspace binding from tool context."""
    if not context:
        return
    from apps.backend.domain.coding.common import (
        workspace_binding_from_context,
        workspace_retrieval_flags,
    )

    ws = workspace_binding_from_context(context)
    if ws is None:
        return
    wid = ws.get("id")
    path = ws.get("path")
    if not wid or not isinstance(path, str) or not path.strip():
        return
    sem_on, _ret = workspace_retrieval_flags(context)
    enqueue_incremental_index(
        str(wid),
        path.strip(),
        rel_paths,
        semantic_index_enabled=sem_on,
        workspace=ws,
    )


def _flush_workspace(workspace_id: str) -> None:
    with _LOCK:
        entry = _PENDING.pop(workspace_id, None)
    if not entry:
        return
    paths = list(entry.get("paths") or [])
    root = str(entry.get("root") or "")
    sem = bool(entry.get("semantic_index_enabled", True))
    if not paths or not root:
        return
    threading.Thread(
        target=_run_incremental_job,
        args=(workspace_id, root, paths, sem),
        daemon=True,
        name=f"incr-index-{workspace_id[:8]}",
    ).start()


def _run_incremental_job(
    workspace_id: str,
    root_path: str,
    rel_paths: list[str],
    semantic_index_enabled: bool,
) -> None:
    try:
        from apps.backend.infrastructure.workspace_retrieval import run_incremental_index

        run_incremental_index(
            workspace_id,
            root_path,
            rel_paths,
            semantic_index_enabled=semantic_index_enabled,
        )
    except Exception:
        logger.exception("incremental index job failed for workspace %s", workspace_id)
