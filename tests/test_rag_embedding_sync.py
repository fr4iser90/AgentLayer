"""Tests for provider-aware RAG embedding model selection."""

from __future__ import annotations

from apps.backend.infrastructure.rag_embedding_sync import (
    rank_embedding_model_ids,
    resolve_rag_embedding_model_from_provider,
)


def test_rank_prefers_embedding_ids() -> None:
    ranked = rank_embedding_model_ids(
        ["gpt-4", "nomic-embed-text", "llama3", "bge-m3"]
    )
    assert ranked[0] in ("nomic-embed-text", "bge-m3")
    assert "gpt-4" in ranked[-2:]


def test_resolve_keeps_current_when_on_provider() -> None:
    model, reason = resolve_rag_embedding_model_from_provider(
        current_model="bge-m3",
        available_models=["gpt-4", "bge-m3"],
    )
    assert model == "bge-m3"
    assert "offered" in reason


def test_resolve_switches_when_current_missing_on_provider() -> None:
    model, reason = resolve_rag_embedding_model_from_provider(
        current_model="nomic-embed-text",
        available_models=["bge-m3", "gpt-4"],
    )
    assert model == "bge-m3"
    assert "not on provider" in reason


def test_resolve_empty_when_no_provider_models() -> None:
    model, reason = resolve_rag_embedding_model_from_provider(
        current_model="",
        available_models=[],
    )
    assert model == ""
    assert "no provider models" in reason


def test_resolve_env_preferred_when_current_missing() -> None:
    model, reason = resolve_rag_embedding_model_from_provider(
        current_model="",
        available_models=["bge-m3", "custom-embed-v1"],
        env_preferred="custom-embed-v1",
    )
    assert model == "custom-embed-v1"
    assert ".env" in reason
