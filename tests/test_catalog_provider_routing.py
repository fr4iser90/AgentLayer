"""Unified catalog provider routing (all stacks use the same code path)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.backend.infrastructure.model_catalog_providers import (
    CatalogProviderSpec,
    db_catalog_provider_id,
    merge_model_catalog_rows,
    route_chat_by_catalog_provider,
)


def test_route_env_provider_spec() -> None:
    spec = CatalogProviderSpec(
        provider_id="provider_1",
        label="Local",
        base_url="http://127.0.0.1:8080",
        api_key="",
        api_header_name="Authorization",
        source="env",
    )
    with patch(
        "apps.backend.infrastructure.model_catalog_providers.get_provider_spec",
        return_value=spec,
    ):
        attempts, stack = route_chat_by_catalog_provider(
            "provider_1",
            "llama3.2",
            "default",
            is_override=True,
        )
    assert stack == "provider_env"
    assert len(attempts) == 1
    url, headers, model = attempts[0]
    assert url.endswith("/v1/chat/completions")
    assert model == "llama3.2"
    assert "Content-Type" in headers


def test_route_admin_provider_spec() -> None:
    spec = CatalogProviderSpec(
        provider_id=db_catalog_provider_id(7),
        label="OpenAI proxy",
        base_url="https://api.example.com/v1",
        api_key="sk-test",
        api_header_name="Authorization",
        model_default="gpt-4o-mini",
        source="db",
        db_endpoint_id=7,
    )
    with patch(
        "apps.backend.infrastructure.model_catalog_providers.get_provider_spec",
        return_value=spec,
    ):
        attempts, stack = route_chat_by_catalog_provider(
            db_catalog_provider_id(7),
            "",
            "default",
            is_override=False,
        )
    assert stack == "provider_admin"
    assert attempts[0][2] == "gpt-4o-mini"


def test_route_unknown_provider_raises() -> None:
    with patch(
        "apps.backend.infrastructure.model_catalog_providers.get_provider_spec",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="Unknown catalog provider"):
            route_chat_by_catalog_provider("anthropic_custom", "claude", "default", False)


def test_merge_same_id_different_providers() -> None:
    a = [{"id": "m", "owned_by": "provider_1"}]
    b = [{"id": "m", "owned_by": "provider_2"}]
    out = merge_model_catalog_rows(a, b)
    assert len(out) == 2
