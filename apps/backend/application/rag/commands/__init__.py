"""RAG write commands."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RagChunkInput:
    index: int
    text: str


@dataclass(frozen=True, slots=True)
class SaveRagDocumentCommand:
    document_id: str
    collection: str
    source_uri: str
    title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    chunks: list[RagChunkInput] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DeleteRagDocumentCommand:
    document_id: str
