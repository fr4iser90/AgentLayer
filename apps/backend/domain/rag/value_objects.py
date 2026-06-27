"""RAG value objects."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RagDocumentId:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "RagDocumentId":
        value = raw.strip()
        if not value:
            raise ValueError("RAG document id must not be blank")
        return cls(value)


@dataclass(frozen=True, slots=True)
class RagCollectionName:
    value: str

    @classmethod
    def parse(cls, raw: str) -> "RagCollectionName":
        value = raw.strip()
        if not value or len(value) > 128:
            raise ValueError("RAG collection name must be 1..128 characters")
        return cls(value)
