"""RAG infrastructure service: chunking, embeddings, ingest, and search."""
from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.settings import operator_settings
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.providers.embedding_chunking import chunk_text_for_embedding
from apps.backend.infrastructure.providers.embedding_client import embed_one

logger = logging.getLogger(__name__)

__all__ = [
    "chunk_text",
    "embed_one",
    "ingest_for_user",
    "search_for_identity",
]


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    chunk_size = max(200, int(chunk_size))
    overlap = max(0, min(int(overlap), chunk_size - 1))
    step = chunk_size - overlap
    out: list[str] = []
    i = 0
    while i < len(t):
        out.append(t[i : i + chunk_size])
        i += step
    return [c for c in out if c.strip()]


def ingest_for_user(
    tenant_id: int,
    user_id: uuid.UUID,
    domain: str,
    title: str,
    text: str,
    source_uri: str | None = None,
    *,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    rs = operator_settings.rag_settings()
    if not rs["enabled"]:
        raise ValueError("RAG is disabled (operator settings)")
    raw = (text or "").strip()
    if not raw:
        raise ValueError("text is required")
    chunks = chunk_text_for_embedding(raw, rs["chunk_size"], rs["chunk_overlap"])
    if not chunks:
        raise ValueError("no chunks after splitting")
    indexed: list[tuple[int, str, list[float]]] = []
    for i, ch in enumerate(chunks):
        emb = embed_one(ch)
        indexed.append((i, ch, emb))
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    doc_id, n = db.rag_document_and_chunks_insert(
        tenant_id,
        user_id,
        domain,
        title,
        source_uri,
        sha,
        indexed,
        workspace_id=workspace_id,
    )
    out: dict[str, Any] = {
        "ok": True,
        "document_id": doc_id,
        "chunk_count": n,
        "domain": (domain or "").strip(),
        "title": (title or "").strip(),
    }
    if workspace_id is not None:
        out["workspace_id"] = str(workspace_id)
    return out


def search_for_identity(
    query: str,
    domain: str | None = None,
    limit: int | None = None,
    *,
    workspace_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    rs = operator_settings.rag_settings()
    if not rs["enabled"]:
        return []
    q = (query or "").strip()
    if not q:
        return []
    emb = embed_one(q)
    tenant_id, user_id = get_identity()
    if user_id is None:
        return []
    lim = limit if limit is not None else int(rs["top_k"])
    if workspace_id is not None:
        return db.rag_vector_search_by_workspace(
            tenant_id,
            user_id,
            workspace_id,
            emb,
            int(lim),
        )
    dom_raw = (domain or "").strip() if domain else ""
    dom_lc = dom_raw.lower()
    tenant_wide = bool(dom_lc and dom_lc in operator_settings.effective_rag_tenant_shared_domains())
    rows = db.rag_vector_search(
        tenant_id,
        user_id,
        emb,
        domain,
        int(lim),
        tenant_wide_domain=tenant_wide,
    )
    if dom_lc == "tenant_knowledge_draft":
        from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
            effective_policy,
        )
        from apps.backend.domain.tenant_profession.policy import (
            CAP_CONTENT_EDITOR,
            CAP_CONTENT_REVIEW,
        )

        policy = effective_policy(user_id, tenant_id)
        if not (policy.has(CAP_CONTENT_EDITOR) or policy.has(CAP_CONTENT_REVIEW)):
            return []
    if dom_lc == "tenant_knowledge" and user_id is not None:
        from apps.backend.application.tenant_profession.use_cases.profession_policy_service import (
            effective_policy,
            filter_rag_hits,
        )

        policy = effective_policy(user_id, tenant_id)
        rows = filter_rag_hits(rows, policy)
    logger.info(
        "rag_search tenant_id=%s user_id=%s domain=%s query_chars=%d hit_count=%d document_ids=%s",
        tenant_id,
        user_id,
        dom_lc or (domain or ""),
        len(q),
        len(rows),
        [r.get("document_id") for r in rows],
    )
    return rows
