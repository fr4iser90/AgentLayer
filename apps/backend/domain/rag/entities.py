"""RAG entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.rag.value_objects import RagCollectionName, RagDocumentId


@dataclass(slots=True)
class RagDocument:
    id: RagDocumentId
    collection: RagCollectionName
    source_uri: str
    title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_uri.strip():
            raise ValueError("RAG document source_uri must not be blank")
        if self.title is not None and not self.title.strip():
            raise ValueError("RAG document title must not be blank")


@dataclass(frozen=True, slots=True)
class RagChunk:
    document_id: RagDocumentId
    index: int
    text: str

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("RAG chunk index must be non-negative")
        if not self.text.strip():
            raise ValueError("RAG chunk text must not be blank")
