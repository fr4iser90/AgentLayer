"""RAG helpers for tools."""

from __future__ import annotations

import types

from apps.backend.infrastructure.rag.rag_core import (
    chunk_text,
    embed_one,
    ingest_for_user,
    search_for_identity,
)

rag = types.SimpleNamespace(
    chunk_text=chunk_text,
    embed_one=embed_one,
    ingest_for_user=ingest_for_user,
    search_for_identity=search_for_identity,
)
