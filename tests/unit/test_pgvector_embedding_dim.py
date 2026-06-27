"""Tests for runtime pgvector dimension alignment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.backend.infrastructure.providers.pgvector_embedding_dim import (
    deployment_pgvector_embedding_dim,
    ensure_pgvector_embedding_dim,
    read_pgvector_column_dim,
)


def _mock_pool(*, fetchone_results: list) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.side_effect = fetchone_results
    cm_cursor = MagicMock()
    cm_cursor.__enter__.return_value = cur
    cm_cursor.__exit__.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cm_cursor
    cm_conn = MagicMock()
    cm_conn.__enter__.return_value = conn
    cm_conn.__exit__.return_value = None
    pool = MagicMock()
    pool.connection.return_value = cm_conn
    return pool


def test_read_pgvector_column_dim_parses_vector_type() -> None:
    pool = _mock_pool(fetchone_results=[("vector(1024)",)])
    with patch("apps.backend.infrastructure.providers.pgvector_embedding_dim.db.pool", return_value=pool):
        assert read_pgvector_column_dim(table="rag_chunks") == 1024


def test_read_pgvector_column_dim_missing_column() -> None:
    pool = _mock_pool(fetchone_results=[(None,)])
    with patch("apps.backend.infrastructure.providers.pgvector_embedding_dim.db.pool", return_value=pool):
        assert read_pgvector_column_dim(table="rag_chunks") is None


def test_ensure_pgvector_noop_when_already_aligned() -> None:
    pool = _mock_pool(fetchone_results=[("vector(1024)",)])
    with patch("apps.backend.infrastructure.providers.pgvector_embedding_dim.db.pool", return_value=pool):
        summary = ensure_pgvector_embedding_dim(1024)
    assert summary["ok"] is True
    assert summary["migrated"] is False
    assert summary["current_dim"] == 1024


def test_ensure_pgvector_migrates_when_dim_differs() -> None:
    pool = _mock_pool(fetchone_results=[("vector(768)",)])
    with patch("apps.backend.infrastructure.providers.pgvector_embedding_dim.db.pool", return_value=pool):
        with patch(
            "apps.backend.infrastructure.settings.operator_settings.set_rag_docs_ingest_fingerprint"
        ) as mock_fp:
            summary = ensure_pgvector_embedding_dim(1024, log_prefix="test")
    assert summary["migrated"] is True
    assert summary["current_dim"] == 768
    assert summary["target_dim"] == 1024
    mock_fp.assert_called_once_with("")


def test_ensure_pgvector_rejects_invalid_dim() -> None:
    with pytest.raises(ValueError, match="32..4096"):
        ensure_pgvector_embedding_dim(16)


def test_deployment_pgvector_embedding_dim_delegates() -> None:
    pool = _mock_pool(fetchone_results=[("vector(768)",)])
    with patch("apps.backend.infrastructure.providers.pgvector_embedding_dim.db.pool", return_value=pool):
        assert deployment_pgvector_embedding_dim() == 768
