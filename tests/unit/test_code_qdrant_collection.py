"""Tests for per-dimension Qdrant code collection routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from apps.backend.infrastructure.codebase.code_qdrant_collection import (
    invalidate_code_qdrant_target_cache,
    resolve_code_qdrant_target,
)


def _collection_json(dim: int) -> dict:
    return {
        "result": {
            "config": {
                "params": {
                    "vectors": {"size": dim, "distance": "Cosine"},
                }
            }
        }
    }


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_code_qdrant_target_cache()
    yield
    invalidate_code_qdrant_target_cache()


@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.operator_settings.rag_settings")
@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.config.QDRANT_URL", "http://qdrant:6333")
def test_resolve_uses_base_when_dim_matches(mock_rag_settings: MagicMock) -> None:
    mock_rag_settings.return_value = {"embedding_dim": 768}

    mock_resp_404 = MagicMock(status_code=404)
    mock_resp_768 = MagicMock(status_code=200)
    mock_resp_768.json.return_value = _collection_json(768)

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [mock_resp_768]

        target = resolve_code_qdrant_target(force=True)

    assert target.collection == "code_symbols"
    assert target.embedding_dim == 768
    assert target.auto_switched is False


@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.operator_settings.rag_settings")
@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.config.QDRANT_URL", "http://qdrant:6333")
def test_resolve_switches_to_dim_suffix_when_base_mismatch(mock_rag_settings: MagicMock) -> None:
    mock_rag_settings.return_value = {"embedding_dim": 1024}

    mock_resp_base = MagicMock(status_code=200)
    mock_resp_base.json.return_value = _collection_json(768)
    mock_resp_alt = MagicMock(status_code=404)

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [mock_resp_base, mock_resp_alt]

        target = resolve_code_qdrant_target(force=True)

    assert target.collection == "code_symbols_1024"
    assert target.embedding_dim == 1024
    assert target.auto_switched is True


@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.operator_settings.rag_settings")
@patch("apps.backend.infrastructure.codebase.code_qdrant_collection.config.QDRANT_URL", "http://qdrant:6333")
def test_resolve_creates_base_when_missing(mock_rag_settings: MagicMock) -> None:
    mock_rag_settings.return_value = {"embedding_dim": 1024}

    mock_resp_404 = MagicMock(status_code=404)

    with patch("httpx.Client") as client_cls:
        client = client_cls.return_value.__enter__.return_value
        client.get.side_effect = [mock_resp_404]

        target = resolve_code_qdrant_target(force=True)

    assert target.collection == "code_symbols"
    assert target.embedding_dim == 1024
    assert "will be created" in target.note
