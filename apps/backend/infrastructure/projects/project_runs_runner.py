"""Background worker for ``project_runs`` (coding agent execution queue)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from apps.backend.infrastructure.platform.poll_loop import PollLoop
from apps.backend.infrastructure.projects import project_runs_store
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.projects.project_runs_store import RunStatus
from apps.backend.infrastructure.codebase.coding_schedule_execution import run_coding_schedule_row

logger = logging.getLogger(__name__)

_POLL_SEC = 6.0
_MAX_BATCH = 5


def start_project_runs_worker() -> None:
    _worker.start()


def stop_project_runs_worker() -> None:
    _worker.stop()


def _tenant_id(row: dict[str, Any]) -> int:
    t = row.get("tenant_id")
    return int(t) if t is not None else 0


def _uid(row: dict[str, Any], key: str) -> uuid.UUID:
    v = row.get(key)
    if isinstance(v, uuid.UUID):
        return v
    return uuid.UUID(str(v))


async def _run_project_run(row: dict[str, Any]) -> tuple[bool, str | None, dict[str, Any] | None]:
    return await run_coding_schedule_row(row, row_kind="project_run")


def _run_queued_runs() -> None:
    worker_on, _ = operator_settings.scheduler_jobs_worker_settings()
    if not worker_on:
        return

    rows = project_runs_store.fetch_queued_runs_coding(limit=_MAX_BATCH)
    for row in rows:
        if _worker.stopping():
            break
        tenant_id = _tenant_id(row)
        run_id = _uid(row, "id")
        if not project_runs_store.mark_running(run_id=run_id, tenant_id=tenant_id):
            continue
        try:
            ok, err, summary = asyncio.run(_run_project_run(row))
        except Exception:
            logger.exception("project_runs: run failed run_id=%s", run_id)
            project_runs_store.mark_done(
                run_id=run_id,
                tenant_id=tenant_id,
                status="failed",
                error="project run execution failed",
                result_json=None,
            )
            continue
        final_status: RunStatus = "succeeded" if ok else "failed"
        project_runs_store.mark_done(
            run_id=run_id,
            tenant_id=tenant_id,
            status=final_status,
            error=err,
            result_json=summary,
        )


_worker = PollLoop(
    name="project-runs-worker",
    iteration=_run_queued_runs,
    poll_sec=_POLL_SEC,
    join_sec=20.0,
    failure_log="project_runs worker iteration failed",
)
