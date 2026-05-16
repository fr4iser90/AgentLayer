"""RAG helpers for tools; implementation lives in ``apps.api.rag``."""

from __future__ import annotations

import types

from apps.backend.api.rag import (
    chunk_text,
    embed_one,
    ingest_for_user,
    ollama_embed_one,
    search_for_identity,
)

rag = types.SimpleNamespace(
    chunk_text=chunk_text,
    embed_one=embed_one,
    ingest_for_user=ingest_for_user,
    ollama_embed_one=ollama_embed_one,
    search_for_identity=search_for_identity,
)
