"""RAG embedding model/dim helpers and short-lived pgvector width cache."""

from __future__ import annotations

import time
from typing import Any


_PGVECTOR_DIM_CACHE: tuple[float, int] | None = None
_PGVECTOR_DIM_CACHE_TTL_SEC = 30.0


def _normalize_rag_embedding_model(raw: Any) -> str:
    return (str(raw or "").strip())[:256]


def _rag_embedding_model_from_row(r: dict[str, Any]) -> str:
    return _normalize_rag_embedding_model(r.get("rag_embedding_model"))


def _coerce_rag_embedding_dim(v: Any) -> int:
    """Return a bounded dim from an explicit value, or ``0`` when unset/invalid."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    if 32 <= n <= 4096:
        return n
    return 0


def _invalidate_pgvector_dim_cache() -> None:
    global _PGVECTOR_DIM_CACHE
    _PGVECTOR_DIM_CACHE = None


def _deployment_pgvector_dim_cached() -> int:
    """Live ``vector(N)`` width from Postgres; ``0`` when unknown (cached briefly)."""
    global _PGVECTOR_DIM_CACHE
    now = time.monotonic()
    if (
        _PGVECTOR_DIM_CACHE is not None
        and now - _PGVECTOR_DIM_CACHE[0] <= _PGVECTOR_DIM_CACHE_TTL_SEC
    ):
        return _PGVECTOR_DIM_CACHE[1]
    dim = 0
    try:
        from apps.backend.infrastructure.providers.pgvector_embedding_dim import deployment_pgvector_embedding_dim

        probed = deployment_pgvector_embedding_dim()
        if probed is not None and 32 <= int(probed) <= 4096:
            dim = int(probed)
    except Exception:
        pass
    _PGVECTOR_DIM_CACHE = (now, dim)
    return dim


def _rag_embedding_dim_from_row(r: dict[str, Any]) -> int:
    """
    Effective embedding width: stored operator setting, else live pgvector column, else ``0`` (unset).
    """
    stored = _coerce_rag_embedding_dim(r.get("rag_embedding_dim"))
    if stored >= 32:
        return stored
    pg = _deployment_pgvector_dim_cached()
    return pg if pg >= 32 else 0
