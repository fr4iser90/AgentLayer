"""Scheduler jobs must stamp last_run_at even when a run fails.

Due-ness is ``COALESCE(last_run_at, created_at) + interval``, so an unstamped failure
leaves the job permanently due and it re-runs on every worker tick.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from apps.backend.infrastructure.scheduling import scheduler_jobs_runner as mod


class _Marks:
    def __init__(self) -> None:
        self.job_ids: list[uuid.UUID] = []

    def __call__(self, *, job_id: uuid.UUID, tenant_id: int) -> bool:
        self.job_ids.append(job_id)
        return True


@pytest.fixture
def job_row() -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "tenant_id": 1,
        "execution_user_id": uuid.uuid4(),
        "title": "nightly digest",
        "instructions": "summarise the board",
        "interval_minutes": 1440,
    }


@pytest.fixture
def marks(monkeypatch: pytest.MonkeyPatch) -> _Marks:
    m = _Marks()
    monkeypatch.setattr(mod.scheduler_jobs_store, "mark_job_last_run", m)
    return m


@pytest.fixture
def notifications(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    import apps.backend.infrastructure.notifications.notifications_service as notif

    monkeypatch.setattr(
        notif,
        "notify_scheduler_job_finished",
        lambda **kw: sent.append(kw),
    )
    return sent


def _patch_chat(monkeypatch: pytest.MonkeyPatch, *, raises: Exception | None) -> None:
    import apps.backend.application.agent_runtime.use_cases.chat_completion as chat_mod
    import apps.backend.infrastructure.agent_runtime.catalog_chat_llm_service as catalog_mod

    async def _chat(*_a: Any, **_k: Any) -> Any:
        if raises is not None:
            raise raises
        return {"ok": True}

    monkeypatch.setattr(chat_mod, "chat_completion", _chat)
    monkeypatch.setattr(catalog_mod, "catalog_llm_body_extras", lambda **_k: {})
    monkeypatch.setattr(mod.db, "user_role", lambda _uid: "user")


def test_failed_chat_job_still_stamps_last_run(
    monkeypatch: pytest.MonkeyPatch,
    job_row: dict[str, Any],
    marks: _Marks,
    notifications: list[dict[str, Any]],
) -> None:
    _patch_chat(monkeypatch, raises=RuntimeError("llm exploded"))

    asyncio.run(mod._run_chat_agent_job(job_row, agent_id="general"))

    assert marks.job_ids == [job_row["id"]]
    assert [n["success"] for n in notifications] == [False]
    assert "llm exploded" in str(notifications[0]["error"])


def test_successful_chat_job_stamps_last_run(
    monkeypatch: pytest.MonkeyPatch,
    job_row: dict[str, Any],
    marks: _Marks,
    notifications: list[dict[str, Any]],
) -> None:
    _patch_chat(monkeypatch, raises=None)

    asyncio.run(mod._run_chat_agent_job(job_row, agent_id="general"))

    assert marks.job_ids == [job_row["id"]]
    assert [n["success"] for n in notifications] == [True]


def test_failed_workspace_job_still_stamps_last_run(
    monkeypatch: pytest.MonkeyPatch,
    job_row: dict[str, Any],
    marks: _Marks,
) -> None:
    async def _run(*_a: Any, **_k: Any) -> tuple[bool, str, None]:
        return False, "workspace missing", None

    monkeypatch.setattr(mod, "run_coding_schedule_row", _run)

    asyncio.run(mod._run_workspace_agent_job(job_row))

    assert marks.job_ids == [job_row["id"]]
