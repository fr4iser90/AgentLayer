"""Repository ports for RAG."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.rag.entities import RagChunk, RagDocument
from apps.backend.domain.rag.value_objects import RagCollectionName, RagDocumentId


class RagDocumentRepository(Protocol):
    def get(self, document_id: RagDocumentId) -> RagDocument | None: ...

    def list_by_collection(self, collection: RagCollectionName, *, limit: int = 100) -> list[RagDocument]: ...

    def save(self, document: RagDocument, chunks: list[RagChunk]) -> RagDocument: ...

    def delete(self, document_id: RagDocumentId) -> None: ...
