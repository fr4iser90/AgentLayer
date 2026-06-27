"""RAG schema validation."""
from __future__ import annotations

from collections.abc import Mapping


def validate_rag_metadata(metadata: Mapping[str, object] | None) -> dict[str, object]:
    if metadata is None:
        return {}
    if len(metadata) > 100:
        raise ValueError("RAG metadata may contain at most 100 keys")
    return {str(key): value for key, value in metadata.items()}


def validate_chunk_text(text: str) -> str:
    value = text.strip()
    if not value:
        raise ValueError("RAG chunk text must not be blank")
    return value
