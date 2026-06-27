"""RAG DTOs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RagDocumentDto:
    document_id: str
    collection: str
    source_uri: str
    title: str | None
    metadata: dict[str, object] = field(default_factory=dict)
