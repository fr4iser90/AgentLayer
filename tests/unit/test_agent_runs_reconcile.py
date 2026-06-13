"""Tests for orphaned agent_runs reconciliation."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure import agent_runs_store


@contextmanager
def _mock_db_cursor(*, rowcount: int):
    cur = MagicMock()
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    with patch("apps.backend.infrastructure.agent_runs_store.db.pool", return_value=pool):
        yield cur, conn


def test_reconcile_orphaned_agent_runs_on_startup() -> None:
    with _mock_db_cursor(rowcount=3) as (cur, conn):
        n = agent_runs_store.reconcile_orphaned_agent_runs_on_startup()

    assert n == 3
    cur.execute.assert_called_once()
    sql, err = cur.execute.call_args[0]
    assert "status = 'running'" in sql
    assert "interrupted" in str(err).lower()
    conn.commit.assert_called_once()


def test_reconcile_orphaned_agent_runs_for_user_excludes_live() -> None:
    uid = uuid.uuid4()
    live = uuid.uuid4()
    with _mock_db_cursor(rowcount=1) as (cur, conn):
        n = agent_runs_store.reconcile_orphaned_agent_runs(
            user_id=uid,
            exclude_run_ids={live},
        )

    assert n == 1
    sql, params = cur.execute.call_args[0]
    assert "user_id = %s" in sql
    assert "NOT (id = ANY" in sql
    assert uid in params
    assert live in params[-1]
    conn.commit.assert_called_once()


def test_actively_running_workspace_ids_empty_without_live_registry() -> None:
    uid = uuid.uuid4()
    with patch(
        "apps.backend.domain.agent_run_cancel.registered_parent_run_ids",
        return_value=frozenset(),
    ):
        assert agent_runs_store.actively_running_workspace_ids_for_user(uid) == set()
