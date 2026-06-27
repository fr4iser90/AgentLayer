"""Infrastructure adapter for docs RAG file ingest."""

from __future__ import annotations

import uuid

from apps.backend.domain import rag_docs_file_ingest as domain
from apps.backend.infrastructure import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.rag_ingest_service import ingest_markdown_paths as _registered_ingest

_ = _registered_ingest  # ensure shared RAG ingest dependencies are registered


class _RagDocsFileIngestDeps:
    effective_docs_root_str = staticmethod(operator_settings.effective_docs_root_str)
    rag_embedding_ready = staticmethod(operator_settings.rag_embedding_ready)
    user_first_admin_id = staticmethod(db.user_first_admin_id)
    user_tenant_id = staticmethod(db.user_tenant_id)

    @staticmethod
    def rag_enabled() -> bool:
        return bool(operator_settings.rag_settings()["enabled"])


domain.register_rag_docs_file_ingest_dependencies(_RagDocsFileIngestDeps())

ingest_markdown_tree = domain.ingest_markdown_tree
resolve_docs_root = domain.resolve_docs_root
run_startup_rag_docs_ingest = domain.run_startup_rag_docs_ingest
