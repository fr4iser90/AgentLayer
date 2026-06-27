"""Unit tests for benchmark bulk delete store helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.benchmarks.benchmark_runs_store import delete_finished_runs


def test_delete_finished_runs_builds_expected_sql() -> None:
    mock_cur = MagicMock()
    mock_cur.rowcount = 3
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)

    with patch("apps.backend.infrastructure.benchmarks.benchmark_runs_store.db") as mock_db:
        mock_db.pool.return_value = mock_pool
        deleted = delete_finished_runs(
            tenant_id=1,
            suite="smoke",
            older_than_days=30,
        )

    assert deleted == 3
    sql = mock_cur.execute.call_args[0][0]
    params = mock_cur.execute.call_args[0][1]
    assert "DELETE FROM benchmark_runs" in sql
    assert "suite = %s" in sql
    assert "created_at < now()" in sql
    assert "queued" not in sql
    assert params == [1, "smoke", 30]
