"""Tests for dynamic rag_embedding_dim resolution (no hardcoded default width)."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure.settings.operator_settings import (
    _coerce_rag_embedding_dim,
    _rag_embedding_dim_from_row,
)


def test_coerce_rejects_out_of_range() -> None:
    assert _coerce_rag_embedding_dim(0) == 0
    assert _coerce_rag_embedding_dim(16) == 0
    assert _coerce_rag_embedding_dim(768) == 768
    assert _coerce_rag_embedding_dim(1024) == 1024


def test_from_row_uses_stored_when_set() -> None:
    row = {"rag_embedding_dim": 768}
    with patch(
        "apps.backend.infrastructure.settings.operator_settings._deployment_pgvector_dim_cached",
        return_value=1024,
    ):
        assert _rag_embedding_dim_from_row(row) == 768


def test_from_row_falls_back_to_pgvector_when_unset() -> None:
    row = {"rag_embedding_dim": 0}
    with patch(
        "apps.backend.infrastructure.settings.operator_settings._deployment_pgvector_dim_cached",
        return_value=1024,
    ):
        assert _rag_embedding_dim_from_row(row) == 1024


def test_from_row_zero_when_nothing_configured() -> None:
    row = {"rag_embedding_dim": 0}
    with patch(
        "apps.backend.infrastructure.settings.operator_settings._deployment_pgvector_dim_cached",
        return_value=0,
    ):
        assert _rag_embedding_dim_from_row(row) == 0
