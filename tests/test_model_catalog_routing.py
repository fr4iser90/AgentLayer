"""Tests for model catalog owned_by inference."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure import model_catalog_routing as mcr


def test_infer_unique_provider() -> None:
    with patch.object(
        mcr,
        "build_model_provider_index",
        return_value={"only-one": ["llama_cpp"]},
    ):
        mcr.invalidate_model_catalog_cache()
        assert mcr.infer_catalog_owned_by("only-one") == "llama_cpp"


def test_infer_ambiguous_returns_none() -> None:
    with patch.object(
        mcr,
        "build_model_provider_index",
        return_value={"dup": ["ollama", "llama_cpp"]},
    ):
        mcr.invalidate_model_catalog_cache()
        assert mcr.infer_catalog_owned_by("dup") is None
