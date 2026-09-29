"""The member listing is the admin listing with one ownership filter added.

``list_jobs_for_user`` used to be a second walk over ``scheduler_jobs``: its own
company pin, its own archive rule, its own dashboard clause, its own ordering. The
rules a caller must not be able to slip — company pinned, archived rows out — were
therefore written twice, and the SELECT differed only in the labels the member must
not receive. Both listings now reach the database through
:func:`scheduler_jobs_store.list_jobs_for_scope`, so this file pins the ownership
filter, the label boundary and the one shared reader that carries everything else.

No live DB: ``db`` is patched at its source and records what reaches it.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from apps.backend.infrastructure.scheduling import scheduler_jobs_store as mod

TENANT = 7
OTHER_TENANT = 9
OWNER = uuid.uuid4()
DASHBOARD = uuid.uuid4()

_OWNER_FILTER = "AND (j.created_by_user_id = %s OR j.execution_user_id = %s)"


class _RecordingCursor:
    def __init__(self, sink: list[tuple[str, Any]]) -> None:
        self._sink = sink

    def execute(self, sql: str, params: Any = None) -> None:
        self._sink.append((" ".join(str(sql).split()), params))

    def fetchall(self) -> list[dict[str, Any]]:
        return []

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


def _member(recorder: _RecordingDb, **overrides: Any) -> tuple[str, Any]:
    """Run the member listing once and return its single statement."""
    mod.list_jobs_for_user(
        tenant_id=TENANT,
        current_user_id=OWNER,
        is_admin=False,
        **overrides,
    )
    assert len(recorder.statements) == 1
    return recorder.statements[0]


def test_member_listing_keeps_the_rows_it_owns(db_recorder: _RecordingDb) -> None:
    sql, params = _member(db_recorder)

    assert "scheduler_jobs" in sql
    assert "j.tenant_id = ANY(%s)" in sql
    assert _OWNER_FILTER in sql
    assert "j.deleted_at IS NULL" in sql
    assert params[0] == [TENANT]
    assert params.count(OWNER) == 2


def test_an_admin_of_the_same_company_sees_every_row(db_recorder: _RecordingDb) -> None:
    mod.list_jobs_for_user(tenant_id=TENANT, current_user_id=OWNER, is_admin=True)

    sql, params = db_recorder.statements[0]
    assert _OWNER_FILTER not in sql
    assert "j.tenant_id = ANY(%s)" in sql
    assert params[0] == [TENANT]


def test_a_member_listing_never_names_the_colleague_behind_a_row(db_recorder: _RecordingDb) -> None:
    sql, _params = _member(db_recorder)

    assert "created_by_display_name" not in sql
    assert "created_by_email" not in sql
    assert "LEFT JOIN tenants" not in sql


def test_the_admin_listing_does_name_them(db_recorder: _RecordingDb) -> None:
    mod.list_jobs_for_scope(tenant_ids=frozenset({TENANT, OTHER_TENANT}))

    sql, params = db_recorder.statements[0]
    assert "created_by_display_name" in sql
    assert "tn.name AS tenant_name" in sql
    assert _OWNER_FILTER not in sql
    assert params[0] == [TENANT, OTHER_TENANT]


def test_a_member_narrowing_to_a_board_stays_on_that_board(db_recorder: _RecordingDb) -> None:
    sql, params = _member(db_recorder, dashboard_id=DASHBOARD)

    assert "AND j.dashboard_id = %s" in sql
    assert "(j.dashboard_id = %s OR j.dashboard_id IS NULL)" not in sql
    assert DASHBOARD in params


def test_the_member_limit_still_caps_at_two_hundred(db_recorder: _RecordingDb) -> None:
    _sql, params = _member(db_recorder, limit=10_000)

    assert params[-1] == 200


def test_both_listings_run_through_the_one_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(mod, "list_jobs_for_scope", lambda **kwargs: seen.append(kwargs) or [])

    mod.list_jobs_for_user(tenant_id=TENANT, current_user_id=OWNER, is_admin=False, dashboard_id=DASHBOARD)
    mod.list_jobs_for_tenant(
        tenant_id=TENANT,
        dashboard_id=None,
        include_global=False,
        execution_target=None,
        enabled=None,
    )

    assert len(seen) == 2
    member, admin = seen
    assert member["tenant_ids"] == frozenset({TENANT})
    assert member["owner_user_id"] == OWNER
    assert member["include_owner_labels"] is False
    assert member["dashboard_id"] == DASHBOARD
    assert admin["tenant_ids"] == frozenset({TENANT})
    assert "owner_user_id" not in admin
    assert "include_owner_labels" not in admin


def test_an_empty_scope_reads_nothing_at_all(db_recorder: _RecordingDb) -> None:
    assert mod.list_jobs_for_scope(tenant_ids=frozenset()) == []
    assert db_recorder.statements == []


def test_a_site_wide_scope_sends_no_company_filter(db_recorder: _RecordingDb) -> None:
    mod.list_jobs_for_scope(tenant_ids=None)

    sql, params = db_recorder.statements[0]
    assert "j.tenant_id = ANY(%s)" not in sql
    assert TENANT not in (params if isinstance(params, list) else [])