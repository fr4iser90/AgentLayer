"""One schedule row is writable by its owner, or by an already-established admin.

All five mutations (enable, update, archive, unarchive, hard-delete) spelled that rule
themselves, so the next mutation that forgets it edits somebody else's schedule and
nothing complains. Every mutation therefore runs through the same three actors here, so
the write right is pinned once and drift in any single mutation goes red.

No live DB: ``db`` is patched at its source and records the statements that reach it —
which is what "refused" has to mean for these paths: the actor is turned away *before*
an UPDATE or DELETE is sent.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.backend.infrastructure.scheduling import scheduler_jobs_store as mod

JOB_ID = uuid.uuid4()
OWNER = uuid.uuid4()
STRANGER = uuid.uuid4()
TENANT = 7


def _job_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": JOB_ID,
        "tenant_id": TENANT,
        "created_by_user_id": OWNER,
        "execution_user_id": OWNER,
        "dashboard_id": None,
        "execution_target": "general_agent",
        "title": "nightly digest",
        "instructions": "summarise the board",
        "interval_minutes": 60,
        "enabled": True,
        "coding_workflow": None,
        "last_run_at": None,
        "deleted_at": None,
    }
    row.update(overrides)
    return row


class _RecordingCursor:
    def __init__(self, sink: list[tuple[str, Any]]) -> None:
        self._sink = sink
        self.rowcount = 1

    def execute(self, sql: str, params: Any = None) -> None:
        self._sink.append((" ".join(str(sql).split()), params))

    def fetchone(self) -> dict[str, Any]:
        return _job_row()

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class _RecordingConnection:
    def __init__(self, sink: list[tuple[str, Any]]) -> None:
        self._sink = sink

    def cursor(self, **_kwargs: Any) -> _RecordingCursor:
        return _RecordingCursor(self._sink)

    def commit(self) -> None:
        return None

    def __enter__(self) -> "_RecordingConnection":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False


class _RecordingDb:
    """Stands in for the ``db`` module: hands out connections, remembers their statements."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, Any]] = []

    def pool(self) -> "_RecordingDb":
        return self

    def connection(self) -> _RecordingConnection:
        return _RecordingConnection(self.statements)


@pytest.fixture
def db_recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingDb:
    fake = _RecordingDb()
    monkeypatch.setattr(mod, "db", fake)
    return fake


def _answers_with(monkeypatch: pytest.MonkeyPatch, row: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    seen: list[tuple[Any, Any]] = []

    def _get_job(job_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        seen.append((job_id, tenant_id))
        return row

    monkeypatch.setattr(mod, "get_job", _get_job)
    return seen


@pytest.fixture
def stored_job(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    return _answers_with(monkeypatch, _job_row())


@pytest.fixture
def no_such_job(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    return _answers_with(monkeypatch, None)


MUTATIONS: dict[str, Any] = {
    "set_enabled": lambda **kw: mod.set_enabled(enabled=False, **kw),
    "update_job": lambda **kw: mod.update_job(
        title="renamed", instructions=None, interval_minutes=None, coding_workflow=None, **kw
    ),
    "archive_job": mod.archive_job,
    "unarchive_job": mod.unarchive_job,
    "hard_delete_job": mod.hard_delete_job,
}

# What each mutation answers when it refused, per its own return convention.
REFUSAL = {
    "set_enabled": None,
    "update_job": None,
    "archive_job": False,
    "unarchive_job": False,
    "hard_delete_job": False,
}


def _mutate(name: str, *, actor_user_id: uuid.UUID, actor_is_admin: bool) -> Any:
    return MUTATIONS[name](
        job_id=JOB_ID,
        tenant_id=TENANT,
        actor_user_id=actor_user_id,
        actor_is_admin=actor_is_admin,
    )


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_owner_may_write_their_schedule(
    mutation: str, db_recorder: _RecordingDb, stored_job: list[tuple[Any, Any]]
) -> None:
    _mutate(mutation, actor_user_id=OWNER, actor_is_admin=False)

    assert len(db_recorder.statements) == 1, "the owner must reach the write"
    sql, params = db_recorder.statements[0]
    assert "scheduler_jobs" in sql
    assert TENANT in tuple(params or ()), "the write must stay tenant-pinned"
    assert stored_job == [(JOB_ID, TENANT)], "the row must be read tenant-pinned first"


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_admin_may_write_any_schedule(
    mutation: str, db_recorder: _RecordingDb, stored_job: list[tuple[Any, Any]]
) -> None:
    _mutate(mutation, actor_user_id=STRANGER, actor_is_admin=True)

    assert len(db_recorder.statements) == 1


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_stranger_never_writes_another_users_schedule(
    mutation: str, db_recorder: _RecordingDb, stored_job: list[tuple[Any, Any]]
) -> None:
    answer = _mutate(mutation, actor_user_id=STRANGER, actor_is_admin=False)

    assert answer == REFUSAL[mutation]
    assert db_recorder.statements == [], "refusal must happen before any UPDATE or DELETE is sent"


@pytest.mark.parametrize("mutation", sorted(MUTATIONS))
def test_missing_row_refuses_without_writing(
    mutation: str, db_recorder: _RecordingDb, no_such_job: list[tuple[Any, Any]]
) -> None:
    answer = _mutate(mutation, actor_user_id=OWNER, actor_is_admin=False)

    assert answer == REFUSAL[mutation]
    assert db_recorder.statements == []


def test_row_without_an_owner_refuses_a_plain_actor(
    db_recorder: _RecordingDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row that names no owner must not fall open to whoever asks."""
    _answers_with(monkeypatch, _job_row(created_by_user_id=None))

    assert (
        mod.archive_job(job_id=JOB_ID, tenant_id=TENANT, actor_user_id=OWNER, actor_is_admin=False)
        is False
    )
    assert db_recorder.statements == []