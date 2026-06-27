"""Generic numbered EMBEDDING_PROVIDER_N_* env parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.embedding_env_providers import parse_embedding_env_providers
from apps.backend.infrastructure.embedding_catalog_providers import (
    invalidate_embedding_provider_specs_cache,
    list_embedding_provider_specs,
)


def test_numbered_embedding_providers() -> None:
    env = {
        "EMBEDDING_PROVIDER_1_BASE_URL": "https://embed-a/v1",
        "EMBEDDING_PROVIDER_1_LABEL": "Primary",
        "EMBEDDING_PROVIDER_2_BASE_URL": "https://embed-b/v1",
    }
    with patch.dict(os.environ, env, clear=False):
        rows = parse_embedding_env_providers()
    assert len(rows) == 2
    assert rows[0].provider_id == "embedding_provider_1"
    assert rows[1].provider_id == "embedding_provider_2"


def test_empty_when_no_providers() -> None:
    with patch.dict(os.environ, {}, clear=True):
        assert parse_embedding_env_providers() == []


def test_numbered_embedding_provider_scans_sparse_high_indexes() -> None:
    env = {
        "EMBEDDING_PROVIDER_1000_BASE_URL": "https://embed-high/v1",
        "EMBEDDING_PROVIDER_1000_LABEL": "High",
    }
    with patch.dict(os.environ, env, clear=True):
        rows = parse_embedding_env_providers()
    assert [row.provider_id for row in rows] == ["embedding_provider_1000"]


def test_embedding_db_endpoint_gets_llm_style_provider_id(monkeypatch) -> None:
    from apps.backend.infrastructure.db import db

    invalidate_embedding_provider_specs_cache()
    monkeypatch.setattr(
        db,
        "operator_provider_endpoints_list_all",
        lambda kind=None: [
            {
                "id": 1,
                "kind": "embedding",
                "sort_order": 0,
                "enabled": True,
                "label": "Embedding",
                "base_url": "https://embed-db.example/v1",
                "api_key": "secret",
                "api_header_name": "X-API-KEY",
                "model_default": "bge-m3",
                "options_json": {},
            }
        ]
        if kind == "embedding"
        else [],
    )
    with patch.dict(os.environ, {}, clear=True):
        specs = list_embedding_provider_specs(force_refresh=True)

    assert [s.provider_id for s in specs] == ["embedding_provider_db_1"]
    assert specs[0].source == "db"
