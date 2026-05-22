"""Background worker for ``project_runs`` (coding agent execution queue)."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from apps.backend.infrastructure import operator_settings, project_runs_store
from apps.backend.infrastructure.coding_schedule_execution import run_coding_schedule_row

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None

_POLL_SEC = 6.0
_MAX_BATCH = 5


def start_project_runs_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_worker_loop, daemon=True, name="project-runs-worker"
    )
    _thread.start()


def stop_project_runs_worker() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=20)


def _tenant_id(row: dict[str, Any]) -> int:
    t = row.get("tenant_id")
    return int(t) if t is not None else 0


def _uid(row: dict[str, Any], key: str) -> uuid.UUID:
    v = row.get(key)
    if isinstance(v, uuid.UUID):
        return v
    return uuid.UUID(str(v))


def _worker_loop() -> None:
    logger.info("project_runs worker thread started")
    while not _stop.is_set():
        if _stop.wait(timeout=_POLL_SEC):
            break
        try:
            worker_on, _ = operator_settings.scheduler_jobs_worker_settings()
            if not worker_on:
                continue

            rows = project_runs_store.fetch_queued_runs_coding(limit=_MAX_BATCH)
            for row in rows:
                if _stop.is_set():
                    break
                tenant_id = _tenant_id(row)
                run_id = _uid(row, "id")
                if not project_runs_store.mark_running(run_id=run_id, tenant_id=tenant_id):
                    continue
                ok, err = asyncio.run(
                    run_coding_schedule_row(row, row_kind="project_run")
                )
                project_runs_store.mark_done(
                    run_id=run_id,
                    tenant_id=tenant_id,
                    status="succeeded" if ok else "failed",
                    error=err,
                )
        except Exception:
            logger.exception("project_runs worker iteration failed")
    logger.info("project_runs worker stopped")
