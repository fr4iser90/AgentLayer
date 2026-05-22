"""Unit tests for :mod:`apps.backend.infrastructure.embedding_client`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

import apps.backend.core.config as cfgmod
from apps.backend.infrastructure import embedding_client


def test_embed_one_success() -> None:
    fake = {"data": [{"embedding": [0.25] * 768, "index": 0}]}
    with (
        patch.object(cfgmod, "EMBEDDING_BASE_URL", "https://llm.example/v1"),
        patch.object(cfgmod, "EMBEDDING_API_HEADER_NAME", "X-API-KEY"),
        patch.object(cfgmod, "EMBEDDING_API_HEADER_VALUE", "secret"),
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


def test_embed_one_requires_embedding_base_url() -> None:
    with patch.object(cfgmod, "EMBEDDING_BASE_URL", ""):
        with pytest.raises(ValueError, match="EMBEDDING_BASE_URL"):
            embedding_client.embed_one("x")


def test_embed_one_dim_mismatch() -> None:
    fake = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    with (
        patch.object(cfgmod, "EMBEDDING_BASE_URL", "https://llm.example/v1"),
        patch.object(cfgmod, "EMBEDDING_API_HEADER_VALUE", ""),
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
    with patch.object(cfgmod, "EMBEDDING_BASE_URL", "https://llm.example.com/v1"):
        url = embedding_client._embedding_models_list_url()
    assert url == "https://llm.example.com/v1/models"


def test_fetch_embedding_models_list_parses_ids() -> None:
    payload = {"data": [{"id": "nomic-embed-text"}, {"id": "bge-m3"}]}
    with (
        patch.object(cfgmod, "EMBEDDING_BASE_URL", "https://llm.example/v1"),
        patch.object(cfgmod, "EMBEDDING_API_HEADER_VALUE", "k"),
        patch(
            "apps.backend.infrastructure.openai_compat_http.http_get_json",
            return_value=(200, "", payload),
        ) as get_json,
    ):
        ids, err = embedding_client.fetch_embedding_models_list()
    assert err is None
    assert ids == ["nomic-embed-text", "bge-m3"]
    assert get_json.call_args.kwargs["headers"]["X-API-KEY"] == "k"


def test_embedding_request_headers_authorization_bearer() -> None:
    with (
        patch.object(cfgmod, "EMBEDDING_API_HEADER_NAME", "Authorization"),
        patch.object(cfgmod, "EMBEDDING_API_HEADER_VALUE", "tok"),
    ):
        h = embedding_client._embedding_request_headers()
    assert h["Authorization"] == "Bearer tok"


def test_embedding_request_headers_from_operator_settings_db() -> None:
    with (
        patch.object(cfgmod, "EMBEDDING_API_HEADER_VALUE", ""),
        patch.object(
            embedding_client.operator_settings,
            "resolved_embedding_api_key",
            return_value="db-secret",
        ),
        patch.object(
            embedding_client.operator_settings,
            "resolved_embedding_api_header_name",
            return_value="X-Custom-Auth",
        ),
    ):
        h = embedding_client._embedding_request_headers()
    assert h["X-Custom-Auth"] == "db-secret"
