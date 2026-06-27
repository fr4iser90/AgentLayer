"""Infrastructure adapter for RAG markdown ingest."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from apps.backend.infrastructure.rag.rag_core import embed_one, ingest_for_user
from apps.backend.domain.rag import ingest_common as domain
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.providers.embedding_chunking import effective_embed_max_input_tokens
from apps.backend.infrastructure.providers.embedding_client import (
    format_embedding_http_error,
    format_embedding_request_error,
    log_embedding_http_error,
)


class _RagIngestDeps:
    rag_settings = staticmethod(operator_settings.rag_settings)
    rag_docs_ingest_fingerprint = staticmethod(operator_settings.rag_docs_ingest_fingerprint)
    set_rag_docs_ingest_fingerprint = staticmethod(operator_settings.set_rag_docs_ingest_fingerprint)
    effective_embed_max_input_tokens = staticmethod(effective_embed_max_input_tokens)
    embed_one = staticmethod(embed_one)
    format_embedding_http_error = staticmethod(format_embedding_http_error)
    format_embedding_request_error = staticmethod(format_embedding_request_error)
    rag_delete_documents_by_tenant_domain = staticmethod(db.rag_delete_documents_by_tenant_domain)
    rag_documents_by_tenant_domain_index = staticmethod(db.rag_documents_by_tenant_domain_index)
    rag_delete_document_by_id = staticmethod(db.rag_delete_document_by_id)

    @staticmethod
    def ingest_for_user(
        tenant_id: int,
        user_id: uuid.UUID,
        domain_name: str,
        title: str,
        text: str,
        source_uri: str,
        *,
        workspace_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        return ingest_for_user(
            tenant_id,
            user_id,
            domain_name,
            title,
            text,
            source_uri,
            workspace_id=workspace_id,
        )

    @staticmethod
    def log_embedding_http_error(exc: httpx.HTTPStatusError, *, context: str) -> None:
        log_embedding_http_error(exc, context=context)


domain.register_rag_ingest_dependencies(_RagIngestDeps())

compute_rag_ingest_fingerprint = domain.compute_rag_ingest_fingerprint
ingest_config_changed = domain.ingest_config_changed
ingest_markdown_paths = domain.ingest_markdown_paths
sha256_text = domain.sha256_text
