"""RAG use cases."""
from __future__ import annotations

from apps.backend.application.rag.commands import DeleteRagDocumentCommand, SaveRagDocumentCommand
from apps.backend.application.rag.dtos import RagDocumentDto
from apps.backend.application.rag.ports import RagDocumentRepository
from apps.backend.application.rag.queries import GetRagDocumentQuery, ListRagDocumentsQuery
from apps.backend.domain.rag.entities import RagChunk, RagDocument
from apps.backend.domain.rag.schemas import validate_chunk_text, validate_rag_metadata
from apps.backend.domain.rag.value_objects import RagCollectionName, RagDocumentId


def _to_dto(document: RagDocument) -> RagDocumentDto:
    return RagDocumentDto(
        document_id=document.id.value,
        collection=document.collection.value,
        source_uri=document.source_uri,
        title=document.title,
        metadata=dict(document.metadata),
    )


def get_rag_document(repo: RagDocumentRepository, query: GetRagDocumentQuery) -> RagDocumentDto | None:
    document = repo.get(RagDocumentId.parse(query.document_id))
    return _to_dto(document) if document else None


def list_rag_documents(repo: RagDocumentRepository, query: ListRagDocumentsQuery) -> list[RagDocumentDto]:
    collection = RagCollectionName.parse(query.collection)
    return [_to_dto(item) for item in repo.list_by_collection(collection, limit=query.limit)]


def save_rag_document(repo: RagDocumentRepository, command: SaveRagDocumentCommand) -> RagDocumentDto:
    document_id = RagDocumentId.parse(command.document_id)
    document = RagDocument(
        id=document_id,
        collection=RagCollectionName.parse(command.collection),
        source_uri=command.source_uri,
        title=command.title,
        metadata=validate_rag_metadata(command.metadata),
    )
    chunks = [
        RagChunk(document_id=document_id, index=item.index, text=validate_chunk_text(item.text))
        for item in command.chunks
    ]
    return _to_dto(repo.save(document, chunks))


def delete_rag_document(repo: RagDocumentRepository, command: DeleteRagDocumentCommand) -> None:
    repo.delete(RagDocumentId.parse(command.document_id))
