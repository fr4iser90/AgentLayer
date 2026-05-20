"""
Background worker for persisted ``scheduler_jobs``.

- ``execution_target=server_periodic``: ``chat_completion`` (productivity tools).
- ``execution_target=coding_agent``: coding agent on a workspace via ``chat_completion``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from apps.backend.domain.identity import reset_identity, set_identity
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


async def _run_server_job(row: dict[str, Any]) -> None:
    from apps.backend.core.config import config
    from apps.backend.domain.agent import chat_completion

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

    ws = row.get("dashboard_id")
    ws_hint = ""
    if ws is not None:
        ws_hint = f"\nDashboard scope (id): {ws}\n"

    sys_prompt = (
        "You are executing a persisted scheduled server job (scheduler_jobs, execution_target=server_periodic). "
        "Follow the instructions. Reply concisely.\n"
        f"{ws_hint}"
    )
    if title:
        sys_prompt += f"Title: {title}\n"
    sys_prompt += f"Instructions:\n{instr[:31000]}"

    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": "Run this scheduled task now."},
        ],
        "stream": False,
        "agent_plain_completion": False,
        "TOOL_DOMAIN": "productivity",
    }
    from apps.backend.domain.catalog_chat_llm import catalog_llm_body_extras

    try:
        body.update(catalog_llm_body_extras(profile_key="agent"))
    except ValueError as exc:
        logger.warning("scheduler_jobs: no catalog LLM — skip job: %s", exc)
        return

    id_tok = set_identity(tenant_id, user_id)
    try:
        await chat_completion(
            body,
            bearer_user_role=role if role in ("user", "admin") else None,
        )
    except Exception:
        logger.exception(
            "scheduler_jobs: server job failed job_id=%s user=%s", job_id, user_id
        )
        return
    finally:
        reset_identity(id_tok)

    if scheduler_jobs_store.mark_job_last_run(job_id=job_id, tenant_id=tenant_id):
        logger.info("scheduler_jobs: finished server job job_id=%s user=%s", job_id, user_id)
    else:
        logger.warning("scheduler_jobs: could not mark last_run_at job_id=%s", job_id)


async def _run_coding_job(row: dict[str, Any]) -> None:
    job_id = _uid(row, "id")
    tenant_id = _tenant_id(row)
    ok, err = await run_coding_schedule_row(row, row_kind="scheduler_job")
    if ok:
        scheduler_jobs_store.mark_job_last_run(job_id=job_id, tenant_id=tenant_id)
        logger.info("scheduler_jobs: finished coding job job_id=%s", job_id)
    else:
        logger.warning(
            "scheduler_jobs: coding job failed job_id=%s: %s (see scheduler_job_runs)",
            job_id,
            err,
        )


def _worker_loop() -> None:
    logger.info("scheduler_jobs worker thread started (operator_settings / Admin → Interfaces)")
    while not _stop.is_set():
        if _stop.wait(timeout=_POLL_SEC):
            break
        try:
            worker_on, _ = operator_settings.scheduler_jobs_worker_settings()
            if not worker_on:
                continue
            for row in scheduler_jobs_store.fetch_due_jobs_server_periodic(limit=_MAX_BATCH):
                if _stop.is_set():
                    break
                try:
                    asyncio.run(_run_server_job(row))
                except Exception:
                    logger.exception("scheduler_jobs: server run failed")
            for row in scheduler_jobs_store.fetch_due_jobs_coding_agent(limit=_MAX_BATCH):
                if _stop.is_set():
                    break
                try:
                    asyncio.run(_run_coding_job(row))
                except Exception:
                    logger.exception("scheduler_jobs: coding run failed")
        except Exception:
            logger.exception("scheduler_jobs worker iteration failed")
    logger.info("scheduler_jobs server worker stopped")
