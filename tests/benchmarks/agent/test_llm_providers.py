"""Benchmark LLM provider list merges .env and DB catalog."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure.benchmarks.benchmark_runner import list_benchmark_llm_providers
from apps.backend.infrastructure.providers.model_catalog_providers import CatalogProviderSpec


def test_list_benchmark_llm_providers_includes_env_without_api_key() -> None:
    env_spec = CatalogProviderSpec(
        provider_id="provider_2",
        label="OLLAMA",
        base_url="http://192.168.1.10:11434",
        api_key="",
        api_header_name="Authorization",
        model_default="qwen2.5:3b",
        source="env",
    )
    db_spec = CatalogProviderSpec(
        provider_id="provider_db_1",
        label="llama.cpp",
        base_url="https://llm.example.com/v1",
        api_key="secret",
        api_header_name="X-API-KEY",
        model_agent="big-model",
        source="db",
        db_endpoint_id=1,
    )

    with (
        patch(
            "apps.backend.infrastructure.providers.model_catalog_providers.list_provider_specs",
            return_value=[db_spec, env_spec],
        ),
        patch("apps.backend.infrastructure.db.db.external_llm_endpoints_list_all") as list_db,
    ):
        list_db.return_value = [{"id": 1, "enabled": True}]
        rows = list_benchmark_llm_providers()

    assert len(rows) == 2
    by_id = {r["catalog_owned_by"]: r for r in rows}
    assert by_id["provider_2"]["label"] == "OLLAMA"
    assert by_id["provider_db_1"]["endpoint_id"] == 1


def test_list_benchmark_llm_providers_dedupes_same_host_for_benchmark_ui_only() -> None:
    env_spec = CatalogProviderSpec(
        provider_id="provider_1",
        label="LLAMA env",
        base_url="https://llm.example.com/v1",
        api_key="k",
        api_header_name="Authorization",
        source="env",
    )
    db_spec = CatalogProviderSpec(
        provider_id="provider_db_1",
        label="LLAMA db",
        base_url="https://llm.example.com",
        api_key="k",
        api_header_name="Authorization",
        source="db",
        db_endpoint_id=1,
    )

    with (
        patch(
            "apps.backend.infrastructure.providers.model_catalog_providers.list_provider_specs",
            return_value=[db_spec, env_spec],
        ),
        patch("apps.backend.infrastructure.db.db.external_llm_endpoints_list_all") as list_db,
    ):
        list_db.return_value = [{"id": 1, "enabled": True}]
        rows = list_benchmark_llm_providers()

    assert len(rows) == 1
    assert rows[0]["catalog_owned_by"] == "provider_db_1"
