"""RAG/memory text chunking capped by embedding server token limits (llama.cpp ubatch, etc.)."""

from __future__ import annotations

import logging
import math
import re
from typing import Any

logger = logging.getLogger(__name__)

# Conservative: dense markdown (~2.3 chars/token observed) → assume ≥0.5 tokens/char.
_ESTIMATE_CHARS_PER_TOKEN = 2.0
_TOKEN_LIMIT_MARGIN = 16
_BATCH_LIMIT_RE = re.compile(r"current batch size:\s*(\d+)", re.IGNORECASE)
_INPUT_TOKENS_RE = re.compile(r"input\s*\(\s*(\d+)\s+tokens\s*\)", re.IGNORECASE)

_runtime_embed_max_tokens: int | None = None


def clear_runtime_embed_max_tokens() -> None:
    global _runtime_embed_max_tokens
    _runtime_embed_max_tokens = None


def set_runtime_embed_max_tokens(value: int | None) -> None:
    global _runtime_embed_max_tokens
    if value is None or value < 32:
        _runtime_embed_max_tokens = None
        return
    prev = _runtime_embed_max_tokens
    _runtime_embed_max_tokens = int(value)
    if prev != _runtime_embed_max_tokens:
        logger.info(
            "embedding max input tokens set to %s (from server error or probe)",
            _runtime_embed_max_tokens,
        )


def parse_embedding_limits_from_error_body(body: str) -> int | None:
    """Extract server batch/token cap from OpenAI-style or llama.cpp error JSON text."""
    if not body:
        return None
    m = _BATCH_LIMIT_RE.search(body)
    if m:
        return int(m.group(1))
    m = _INPUT_TOKENS_RE.search(body)
    if m:
        # Observed input exceeded limit; cap is at or below this (server may not state batch).
        return max(32, int(m.group(1)) - 1)
    return None


def remember_embedding_limits_from_error_body(body: str) -> int | None:
    limit = parse_embedding_limits_from_error_body(body)
    if limit is not None:
        set_runtime_embed_max_tokens(limit)
    return limit


def configured_embed_max_input_tokens() -> int:
    from apps.backend.core import config as app_config

    return max(32, int(app_config.EMBEDDING_MAX_INPUT_TOKENS))


def effective_embed_max_input_tokens() -> int:
    """Tokens we must not exceed per ``/v1/embeddings`` request (after margin)."""
    cap = configured_embed_max_input_tokens()
    if _runtime_embed_max_tokens is not None:
        cap = min(cap, _runtime_embed_max_tokens)
    return max(32, cap - _TOKEN_LIMIT_MARGIN)


def estimate_embedding_tokens(text: str) -> int:
    raw = (text or "").strip()
    if not raw:
        return 0
    return max(1, math.ceil(len(raw) / _ESTIMATE_CHARS_PER_TOKEN))


def max_chunk_chars_for_embedding(*, char_cap: int, max_input_tokens: int | None = None) -> int:
    """Character budget for one chunk: min(admin rag_chunk_size, token-derived cap)."""
    limit = max_input_tokens if max_input_tokens is not None else effective_embed_max_input_tokens()
    token_chars = int(limit * _ESTIMATE_CHARS_PER_TOKEN)
    return max(200, min(int(char_cap), token_chars))


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Character-based chunker (same algorithm as ``apps.backend.api.rag.chunk_text``)."""
    t = (text or "").strip()
    if not t:
        return []
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    step = chunk_size - overlap
    out: list[str] = []
    i = 0
    while i < len(t):
        out.append(t[i : i + chunk_size])
        i += step
    return [c for c in out if c.strip()]


def chunk_text_for_embedding(
    text: str,
    chunk_size: int,
    overlap: int,
    *,
    max_input_tokens: int | None = None,
) -> list[str]:
    """Split text for RAG ingest; never exceeds embedding server token budget."""
    cap = max_chunk_chars_for_embedding(char_cap=chunk_size, max_input_tokens=max_input_tokens)
    ov = min(int(overlap), max(0, cap - 1))
    if int(chunk_size) > cap and int(chunk_size) > 0:
        ov = min(ov, max(0, int(overlap * cap / int(chunk_size))))
    return chunk_text(text, cap, ov)


def truncate_text_for_embedding(text: str, *, max_input_tokens: int | None = None) -> str:
    """Single-shot embed (memory, tool ranking): trim to token-safe length."""
    raw = (text or "").strip()
    if not raw:
        return raw
    limit = max_input_tokens if max_input_tokens is not None else effective_embed_max_input_tokens()
    if estimate_embedding_tokens(raw) <= limit:
        return raw
    max_chars = max_chunk_chars_for_embedding(char_cap=len(raw), max_input_tokens=limit)
    trimmed = raw[:max_chars].strip()
    logger.warning(
        "embedding input truncated chars %s -> %s (max_tokens~%s)",
        len(raw),
        len(trimmed),
        limit,
    )
    return trimmed
