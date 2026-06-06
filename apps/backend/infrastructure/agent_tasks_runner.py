"""Background worker: run ``agent_tasks`` with status=queued (assigned to general)."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from typing import Any

from apps.backend.domain.identity import reset_identity, set_identity
from apps.backend.infrastructure import agent_tasks_store
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None

_POLL_SEC = 30.0
_MAX_BATCH = 3
_RUNNABLE_AGENTS = frozenset({"general"})


def start_agent_tasks_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(
        target=_worker_loop, daemon=True, name="agent-tasks-worker"
    )
    _thread.start()


def stop_agent_tasks_worker() -> None:
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=20)


def _worker_loop() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while not _stop.is_set():
            try:
                loop.run_until_complete(_poll_once())
            except Exception:
                logger.exception("agent_tasks worker poll failed")
            _stop.wait(_POLL_SEC)
    finally:
        loop.close()


async def _poll_once() -> None:
    rows = agent_tasks_store.fetch_queued_tasks(limit=_MAX_BATCH)
    for row in rows:
        aid = str(row.get("assigned_agent_id") or "general").strip().lower()
        if aid not in _RUNNABLE_AGENTS:
            continue
        await _run_task_row(row)


async def _run_task_row(row: dict[str, Any]) -> None:
    from apps.backend.domain.agent import chat_completion
    from apps.backend.domain.agent_task_prompt import format_requirements_block
    from apps.backend.domain.catalog_chat_llm import catalog_llm_body_extras

    tenant_id = int(row.get("tenant_id") or 0)
    user_id = row.get("created_by_user_id")
    if not isinstance(user_id, uuid.UUID):
        user_id = uuid.UUID(str(user_id))
    task_id = row.get("id")
    if not isinstance(task_id, uuid.UUID):
        task_id = uuid.UUID(str(task_id))

    claimed = agent_tasks_store.update_task(
        task_id=task_id,
        tenant_id=tenant_id,
        status="in_progress",
    )
    if not claimed:
        return

    goal = str(row.get("goal") or "").strip()
    reqs = row.get("requirements")
    req_block = format_requirements_block(reqs)
    user_content = "\n\n".join(
        part
        for part in (
            "Execute this agent task now.",
            f"task_id: {task_id}",
            f"Goal: {goal}",
            req_block,
            (
                "Workflow: use delegate to security_auditor for SSC resolve-scan per repo_url; "
                "then dashboard.list_update to write scan fields on each board row. "
                "Do not redesign layout unless the goal requires it."
            ),
        )
        if part
    )

    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": user_content}],
        "stream": False,
        "agent_id": "general",
        "agent_plain_completion": False,
        "agent_permission_ask": False,
        "agent_unattended": True,
        "agent_active_task_id": str(task_id),
    }

    for key in ("dashboard_id",):
        if isinstance(reqs, list):
            for ln in reqs:
                low = str(ln).strip().lower()
                if low.startswith(f"{key}:"):
                    val = str(ln).split(":", 1)[1].strip()
                    if val:
                        body["agent_dashboard_context"] = {"dashboard_id": val}
                    break

    try:
        body.update(catalog_llm_body_extras(profile_key="agent"))
    except ValueError as exc:
        logger.warning("agent_tasks: no catalog LLM — skip task %s: %s", task_id, exc)
        agent_tasks_store.update_task(
            task_id=task_id, tenant_id=tenant_id, status="blocked"
        )
        return

    role = db.user_role(user_id)
    id_tok = set_identity(tenant_id, user_id)
    failed = False
    try:
        await chat_completion(
            body,
            bearer_user_role=role if role in ("user", "admin") else None,
        )
    except Exception:
        failed = True
        logger.exception("agent_tasks: run failed task_id=%s", task_id)
    finally:
        reset_identity(id_tok)

    agent_tasks_store.update_task(
        task_id=task_id,
        tenant_id=tenant_id,
        status="failed" if failed else "done",
    )
