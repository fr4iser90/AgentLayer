"""Infrastructure adapter for workspace-scoped RAG ingest."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.rag.rag_core import embed_one, ingest_for_user
from apps.backend.domain.rag import workspace_ingest as domain
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.db import db


class _WorkspaceRagIngestDeps:
    rag_settings = staticmethod(operator_settings.rag_settings)
    embed_one = staticmethod(embed_one)
    rag_delete_documents_by_workspace = staticmethod(db.rag_delete_documents_by_workspace)

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


domain.register_workspace_rag_ingest_dependencies(_WorkspaceRagIngestDeps())

WORKSPACE_RAG_DOMAIN = domain.WORKSPACE_RAG_DOMAIN
ingest_workspace_markdown_tree = domain.ingest_workspace_markdown_tree
