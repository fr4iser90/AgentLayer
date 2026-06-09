"""Tests for embedding token-aware chunking."""

from __future__ import annotations

from apps.backend.infrastructure import embedding_chunking as ec


def test_parse_batch_limit_from_llamacpp_error() -> None:
    body = (
        '{"error":{"message":"input (523 tokens) is too large to process. '
        'increase the physical batch size (current batch size: 512)"}}'
    )
    assert ec.parse_embedding_limits_from_error_body(body) == 512


def test_max_chunk_chars_caps_dense_markdown() -> None:
    # 512 tokens - 16 margin = 496; * 2.0 chars/token = 992
    assert ec.max_chunk_chars_for_embedding(char_cap=1200, max_input_tokens=496) == 992


def test_chunk_text_for_embedding_splits_under_cap() -> None:
    text = "x" * 2500
    chunks = ec.chunk_text_for_embedding(text, 1200, 200, max_input_tokens=496)
    assert all(len(c) <= 992 for c in chunks)
    assert len(chunks) >= 3


def test_operator_agent_dense_chunk_fits_budget() -> None:
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "docs/features/operator-agent.md"
    raw = path.read_text(encoding="utf-8").strip()
    chunks = ec.chunk_text_for_embedding(raw, 1200, 200, max_input_tokens=496)
    assert chunks
    for ch in chunks:
        assert ec.estimate_embedding_tokens(ch) <= 496
