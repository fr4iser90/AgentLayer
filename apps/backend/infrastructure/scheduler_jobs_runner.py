"""
Background worker for persisted ``scheduler_jobs``.

``execution_target`` is a registry ``agent_id`` (see ``scheduler_targets``).
Workspace agents use ``run_coding_schedule_row``; others use ``chat_completion``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.domain.scheduler_targets import (
    is_agent_schedulable,
    normalize_execution_target,
)
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure import scheduler_jobs_store
from apps.backend.infrastructure.coding_schedule_execution import run_coding_schedule_row
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None

_POLL_SEC = 45.0
_MAX_BATCH = 5


def start_scheduler_jobs_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_worker_loop, daemon=True, name="scheduler-jobs-server-worker"
    )
    _thread.start()


def stop_scheduler_jobs_worker() -> None:
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


async def _run_chat_agent_job(row: dict[str, Any], *, agent_id: str) -> None:
    from apps.backend.domain.agent import chat_completion
    from apps.backend.domain.catalog_chat_llm import catalog_llm_body_extras

    tenant_id = _tenant_id(row)
    user_id = _uid(row, "execution_user_id")
    job_id = _uid(row, "id")
    role = db.user_role(user_id)

    title = (str(row.get("title") or "").strip()) or None
    instr = str(row.get("instructions") or "").strip()
    if not instr:
        logger.warning("scheduler_jobs: empty instructions job_id=%s — skipping", job_id)
        scheduler_jobs_store.mark_job_last_run(job_id=job_id, tenant_id=tenant_id)
        return

    user_parts = [
        "Run this scheduled task now.",
        f"Job id: {job_id}",
    ]
    if title:
        user_parts.append(f"Title: {title}")
    user_parts.append(f"Instructions:\n{instr[:31000]}")

    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": "\n\n".join(user_parts)}],
        "stream": False,
        "agent_id": agent_id,
        "agent_plain_completion": False,
        "agent_permission_ask": False,
        "agent_unattended": True,
    }

    dash = row.get("dashboard_id")
    if dash is not None:
        body["agent_dashboard_context"] = {"dashboard_id": str(dash)}

    try:
        body.update(catalog_llm_body_extras(profile_key="agent"))
    except ValueError as exc:
        logger.warning("scheduler_jobs: no catalog LLM — skip job: %s", exc)
        return

    from apps.backend.domain.identity import llm_queue_source_scope, reset_identity, set_identity

    id_tok = set_identity(tenant_id, user_id)
    failed = False
    err_text: str | None = None
    try:
        with llm_queue_source_scope("scheduler"):
            await chat_completion(
                body,
                bearer_user_role=role if role in ("user", "admin") else None,
            )
    except Exception as e:
        failed = True
        err_text = str(e)[:500] if str(e) else "chat job failed"
        logger.exception(
            "scheduler_jobs: chat job failed job_id=%s user=%s agent_id=%s",
            job_id,
            user_id,
            agent_id,
        )
    finally:
        reset_identity(id_tok)

    if failed:
        from apps.backend.infrastructure.notifications_service import notify_scheduler_job_finished

        notify_scheduler_job_finished(
            tenant_id=tenant_id,
            user_id=user_id,
            row=row,
            success=False,
            error=err_text,
        )
        return

    if scheduler_jobs_store.mark_job_last_run(job_id=job_id, tenant_id=tenant_id):
        logger.info(
            "scheduler_jobs: finished job job_id=%s user=%s agent_id=%s",
            job_id,
            user_id,
            agent_id,
        )
        from apps.backend.infrastructure.notifications_service import notify_scheduler_job_finished

        notify_scheduler_job_finished(
            tenant_id=tenant_id,
            user_id=user_id,
            row=row,
            success=True,
        )
    else:
        logger.warning("scheduler_jobs: could not mark last_run_at job_id=%s", job_id)


async def _run_workspace_agent_job(row: dict[str, Any]) -> None:
    job_id = _uid(row, "id")
    tenant_id = _tenant_id(row)
    ok, err, _summary = await run_coding_schedule_row(row, row_kind="scheduler_job")
    if ok:
        scheduler_jobs_store.mark_job_last_run(job_id=job_id, tenant_id=tenant_id)
        logger.info("scheduler_jobs: finished workspace job job_id=%s", job_id)
    else:
        logger.warning(
            "scheduler_jobs: workspace job failed job_id=%s: %s (see scheduler_job_runs)",
            job_id,
            err,
        )


async def _run_scheduled_job(row: dict[str, Any]) -> None:
    from apps.backend.domain.agent_registry import get_agent_registry

    agent_id = normalize_execution_target(str(row.get("execution_target") or ""))
    if not agent_id or not is_agent_schedulable(agent_id):
        logger.warning(
            "scheduler_jobs: skip job_id=%s — invalid or non-schedulable execution_target=%r",
            row.get("id"),
            row.get("execution_target"),
        )
        return

    agent = get_agent_registry().get_agent(agent_id)
    if not agent:
        logger.warning(
            "scheduler_jobs: skip job_id=%s — unknown agent_id=%s",
            row.get("id"),
            agent_id,
        )
        return

    if agent.get("requires_workspace"):
        await _run_workspace_agent_job(row)
    else:
        await _run_chat_agent_job(row, agent_id=agent_id)


def _worker_loop() -> None:
    logger.info("scheduler_jobs worker thread started (operator_settings / Admin → Interfaces)")
    while not _stop.is_set():
        if _stop.wait(timeout=_POLL_SEC):
            break
        try:
            worker_on, _ = operator_settings.scheduler_jobs_worker_settings()
            if not worker_on:
                continue
            for row in scheduler_jobs_store.fetch_due_jobs(limit=_MAX_BATCH):
                if _stop.is_set():
                    break
                try:
                    asyncio.run(_run_scheduled_job(row))
                except Exception:
                    logger.exception("scheduler_jobs: run failed job_id=%s", row.get("id"))
        except Exception:
            logger.exception("scheduler_jobs worker iteration failed")
    logger.info("scheduler_jobs server worker stopped")
