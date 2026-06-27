"""Extractor provider env parsing."""

from __future__ import annotations

import os
from unittest.mock import patch

from apps.backend.infrastructure.extractor_catalog_providers import (
    get_extractor_provider_spec,
    invalidate_extractor_provider_specs_cache,
    list_extractor_provider_specs,
)
from apps.backend.infrastructure.extractor_env_providers import parse_extractor_env_providers


def test_parse_extractor_env_provider(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_NAME", "agents-k1")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_BASE_URL", "https://extractor.example/v1")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_API_HEADER_NAME", "X-API-KEY")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_API_KEY", "secret")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_MODEL", "InternScience/Agents-K1")

    rows = parse_extractor_env_providers()

    assert rows[0].provider_id == "agents-k1"
    assert rows[0].base_url == "https://extractor.example/v1"
    assert rows[0].api_header_name == "X-API-KEY"
    assert rows[0].model_default == "InternScience/Agents-K1"


def test_parse_extractor_env_provider_scans_sparse_high_indexes():
    with patch.dict(os.environ, {"EXTRACTOR_PROVIDER_1000_BASE_URL": "https://extractor-high.example/v1"}, clear=True):
        rows = parse_extractor_env_providers()

    assert [row.provider_id for row in rows] == ["extractor_provider_1000"]


def test_extractor_catalog_first_provider(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_NAME", "agents-k1")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_BASE_URL", "https://extractor.example/v1")
    monkeypatch.setenv("EXTRACTOR_PROVIDER_1_MODEL", "InternScience/Agents-K1")
    invalidate_extractor_provider_specs_cache()

    specs = list_extractor_provider_specs(force_refresh=True)
    spec = get_extractor_provider_spec(None)

    assert specs
    assert spec is not None
    assert spec.provider_id == "agents-k1"


def test_extractor_catalog_db_endpoint_provider(monkeypatch):
    for key in (
        "EXTRACTOR_PROVIDER_1_NAME",
        "EXTRACTOR_PROVIDER_1_BASE_URL",
        "EXTRACTOR_PROVIDER_1_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    from apps.backend.infrastructure.db import db

    monkeypatch.setattr(
        db,
        "operator_provider_endpoints_list_all",
        lambda kind=None: [
            {
                "id": 1,
                "kind": "extractor",
                "sort_order": 0,
                "enabled": True,
                "label": "Extractor",
                "base_url": "https://db-extractor.example/v1",
                "api_key": "secret",
                "api_header_name": "Authorization",
                "model_default": "small-extractor",
                "options_json": {"timeout_sec": 42},
            }
        ]
        if kind == "extractor"
        else [],
    )
    invalidate_extractor_provider_specs_cache()

    specs = list_extractor_provider_specs(force_refresh=True)
    spec = get_extractor_provider_spec(None)

    assert [s.provider_id for s in specs] == ["extractor_provider_db_1"]
    assert spec is not None
    assert spec.provider_id == "extractor_provider_db_1"
    assert spec.base_url == "https://db-extractor.example/v1"
    assert spec.model_default == "small-extractor"
    assert spec.timeout_sec == 42

