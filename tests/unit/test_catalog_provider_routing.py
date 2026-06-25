"""Unified catalog provider routing (all stacks use the same code path)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.backend.infrastructure.model_catalog_providers import (
    CatalogProviderSpec,
    _filter_chat_visible_models,
    _parse_models_payload,
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
    url, headers, model, provider_id = attempts[0]
    assert url.endswith("/v1/chat/completions")
    assert model == "llama3.2"
    assert provider_id == "provider_1"
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
    assert stack == "provider_db"
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


def test_parse_models_payload_keeps_modalities_and_context() -> None:
    rows = _parse_models_payload(
        {
            "data": [
                {
                    "id": "llava.gguf",
                    "architecture": {
                        "input_modalities": ["text", "image"],
                        "output_modalities": ["text"],
                    },
                    "meta": {"n_ctx": 131072},
                }
            ]
        },
        "provider_1",
    )

    assert rows == [
        {
            "id": "llava.gguf",
            "object": "model",
            "owned_by": "provider_1",
            "context_length": 131072,
            "capabilities": {
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
        }
    ]


def test_filter_chat_visible_models_hides_explicit_prefs() -> None:
    rows = [
        {"id": "visible.gguf", "owned_by": "provider_1"},
        {"id": "hidden.gguf", "owned_by": "provider_1"},
    ]
    with patch(
        "apps.backend.infrastructure.db.db.model_catalog_visible_index",
        return_value={("provider_1", "hidden.gguf"): False},
    ):
        assert _filter_chat_visible_models(rows) == [{"id": "visible.gguf", "owned_by": "provider_1"}]
