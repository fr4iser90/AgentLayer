"""Unit tests for :mod:`apps.backend.infrastructure.embedding_client`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

import apps.backend.core.config as cfgmod
from apps.backend.infrastructure import embedding_client
from apps.backend.infrastructure.embedding_catalog_providers import EmbeddingProviderSpec


def _spec(**kwargs: object) -> EmbeddingProviderSpec:
    defaults = {
        "provider_id": "embedding_provider_1",
        "label": "Embed",
        "base_url": "https://llm.example/v1",
        "api_key": "secret",
        "api_header_name": "X-API-KEY",
    }
    defaults.update(kwargs)
    return EmbeddingProviderSpec(**defaults)  # type: ignore[arg-type]


def test_embed_one_success() -> None:
    fake = {"data": [{"embedding": [0.25] * 768, "index": 0}]}
    with (
        patch.object(embedding_client, "resolve_active_embedding_spec", return_value=_spec()),
        patch.object(embedding_client, "http_post_json", return_value=fake) as post,
        patch.object(
            embedding_client.operator_settings,
            "rag_settings",
            return_value={
                "embedding_model": "embed-model",
                "embed_timeout_sec": 30.0,
                "embedding_dim": 768,
            },
        ),
    ):
        vec = embedding_client.embed_one("hello world")
    assert len(vec) == 768
    url, body = post.call_args[0]
    assert url.endswith("/embeddings")
    assert "llm.example" in url
    assert post.call_args[1]["headers"]["X-API-KEY"] == "secret"


def test_embed_one_requires_provider() -> None:
    with (
        patch.object(embedding_client, "resolve_active_embedding_spec", return_value=None),
        patch.object(
            embedding_client.operator_settings,
            "rag_settings",
            return_value={"embedding_model": "m", "embed_timeout_sec": 30.0, "embedding_dim": 768},
        ),
    ):
        with pytest.raises(ValueError, match="Embeddings require"):
            embedding_client.embed_one("x")


def test_embed_one_dim_mismatch() -> None:
    fake = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    with (
        patch.object(embedding_client, "resolve_active_embedding_spec", return_value=_spec(api_key="")),
        patch.object(embedding_client, "http_post_json", return_value=fake),
        patch.object(
            embedding_client.operator_settings,
            "rag_settings",
            return_value={
                "embedding_model": "m",
                "embed_timeout_sec": 30.0,
                "embedding_dim": 768,
            },
        ),
    ):
        with pytest.raises(ValueError, match="rag_embedding_dim"):
            embedding_client.embed_one("x")


def test_strip_env_value_removes_quotes() -> None:
    assert embedding_client._strip_env_value('"abc"') == "abc"
    assert embedding_client._strip_env_value("  noquotes  ") == "noquotes"


def test_embedding_models_list_url_no_double_v1() -> None:
    with patch.object(embedding_client, "resolve_active_embedding_spec", return_value=_spec()):
        url = embedding_client._embedding_models_list_url()
    assert url == "https://llm.example/v1/models"


def test_fetch_embedding_models_list_parses_ids() -> None:
    payload = {"data": [{"id": "nomic-embed-text"}, {"id": "bge-m3"}]}
    with (
        patch.object(embedding_client, "resolve_active_embedding_spec", return_value=_spec()),
        patch(
            "apps.backend.infrastructure.openai_compat_http.http_get_json",
            return_value=(200, "", payload),
        ) as get_json,
    ):
        ids, err = embedding_client.fetch_embedding_models_list()
    assert err is None
    assert ids == ["nomic-embed-text", "bge-m3"]
    assert get_json.call_args.kwargs["headers"]["X-API-KEY"] == "secret"


def test_embedding_request_headers_authorization_bearer() -> None:
    spec = _spec(api_header_name="Authorization", api_key="tok")
    h = embedding_client._auth_headers_for_spec(spec)
    assert h["Authorization"] == "Bearer tok"


def test_embedding_request_headers_from_spec() -> None:
    spec = _spec(api_key="db-secret", api_header_name="X-Custom-Auth")
    h = embedding_client._auth_headers_for_spec(spec)
    assert h["X-Custom-Auth"] == "db-secret"


def test_format_embedding_http_error_includes_response_body() -> None:
    request = httpx.Request("POST", "https://embed.example/v1/embeddings")
    response = httpx.Response(500, request=request, text='{"error":"cuda OOM"}')
    exc = httpx.HTTPStatusError("Server error", request=request, response=response)
    msg = embedding_client.format_embedding_http_error(exc)
    assert "status=500" in msg
    assert "embed.example" in msg
    assert "cuda OOM" in msg
