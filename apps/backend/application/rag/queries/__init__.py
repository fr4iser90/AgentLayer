"""RAG read queries."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GetRagDocumentQuery:
    document_id: str


@dataclass(frozen=True, slots=True)
class ListRagDocumentsQuery:
    collection: str
    limit: int = 100
