"""Tests for benchmark_runs_store."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.benchmarks.benchmark_runs_store import reconcile_orphaned_runs_on_startup


@contextmanager
def _mock_db_cursor(*, rowcount: int):
    cur = MagicMock()
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    pool = MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    with patch("apps.backend.infrastructure.benchmarks.benchmark_runs_store.db.pool", return_value=pool):
        yield cur, conn


def test_reconcile_orphaned_runs_on_startup_marks_queued_and_running() -> None:
    with _mock_db_cursor(rowcount=2) as (cur, conn):
        n = reconcile_orphaned_runs_on_startup()

    assert n == 2
    cur.execute.assert_called_once()
    sql, err = cur.execute.call_args[0]
    assert "queued" in sql and "running" in sql
    assert "interrupted" in str(err).lower()
    conn.commit.assert_called_once()


def test_reconcile_orphaned_runs_on_startup_no_op() -> None:
    with _mock_db_cursor(rowcount=0):
        assert reconcile_orphaned_runs_on_startup() == 0
