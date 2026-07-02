from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db.db import pool


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"

def rag_document_and_chunks_insert(
    tenant_id: int,
    user_id: uuid.UUID,
    domain: str,
    title: str,
    source_uri: str | None,
    content_sha256: str,
    chunks: list[tuple[int, str, list[float]]],
    *,
    workspace_id: uuid.UUID | None = None,
) -> tuple[int, int]:
    """
    Insert one ``rag_documents`` row and its chunks (each with embedding).
    Returns ``(document_id, chunk_count)``. Caller must validate embedding dims.
    """
    if not chunks:
        raise ValueError("chunks must be non-empty")
    domain = (domain or "").strip()
    title = (title or "").strip()
    uri = (source_uri or "").strip() or None
    sha = (content_sha256 or "").strip() or None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_documents
                  (tenant_id, user_id, workspace_id, domain, title, source_uri, content_sha256)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tenant_id, user_id, workspace_id, domain, title, uri, sha),
            )
            doc_id = int(cur.fetchone()[0])
            for idx, content, emb in chunks:
                cur.execute(
                    """
                    INSERT INTO rag_chunks (document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    """,
                    (doc_id, int(idx), content, _vector_literal(emb)),
                )
        conn.commit()
    return doc_id, len(chunks)


def rag_delete_documents_by_workspace(tenant_id: int, workspace_id: uuid.UUID) -> int:
    """Delete all RAG documents for a workspace (cascades to chunks)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_documents
                WHERE tenant_id = %s AND workspace_id = %s
                """,
                (tenant_id, workspace_id),
            )
            n = cur.rowcount or 0
        conn.commit()
    return int(n)


def rag_documents_by_tenant_domain_index(
    tenant_id: int,
    domain: str,
    *,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, dict[str, Any]]:
    """``source_uri`` → ``{id, content_sha256}`` for incremental ingest."""
    dom = (domain or "").strip().lower()
    if not dom:
        return {}
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if workspace_id is None:
                cur.execute(
                    """
                    SELECT id, source_uri, content_sha256
                    FROM rag_documents
                    WHERE tenant_id = %s
                      AND lower(trim(domain)) = %s
                      AND workspace_id IS NULL
                      AND source_uri IS NOT NULL
                      AND trim(source_uri) <> ''
                    """,
                    (tenant_id, dom),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source_uri, content_sha256
                    FROM rag_documents
                    WHERE tenant_id = %s
                      AND lower(trim(domain)) = %s
                      AND workspace_id = %s
                      AND source_uri IS NOT NULL
                      AND trim(source_uri) <> ''
                    """,
                    (tenant_id, dom, workspace_id),
                )
            rows = cur.fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        uri = str(r.get("source_uri") or "").strip()
        if not uri:
            continue
        out[uri] = {
            "id": int(r["id"]),
            "content_sha256": (str(r.get("content_sha256") or "").strip() or None),
        }
    return out


def rag_delete_document_by_id(document_id: int) -> bool:
    """Delete one document and its chunks."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_documents WHERE id = %s", (int(document_id),))
            n = cur.rowcount or 0
        conn.commit()
    return n > 0


def rag_delete_documents_by_source_uri(
    tenant_id: int,
    domain: str,
    source_uri: str,
) -> int:
    """Delete RAG documents matching tenant, domain, and exact source_uri."""
    dom = (domain or "").strip().lower()
    uri = (source_uri or "").strip()
    if not dom or not uri:
        return 0
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_documents
                WHERE tenant_id = %s
                  AND lower(trim(domain)) = %s
                  AND source_uri = %s
                  AND workspace_id IS NULL
                """,
                (tenant_id, dom, uri),
            )
            n = cur.rowcount or 0
        conn.commit()
    return int(n)


def rag_delete_documents_by_tenant_domain(tenant_id: int, domain: str) -> int:
    """Delete all ``rag_documents`` for a tenant and domain (case-insensitive). Cascades to chunks."""
    dom = (domain or "").strip().lower()
    if not dom:
        return 0
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_documents
                WHERE tenant_id = %s AND lower(trim(domain)) = %s
                """,
                (tenant_id, dom),
            )
            n = cur.rowcount or 0
        conn.commit()
    return int(n)


def rag_vector_search_by_workspace(
    tenant_id: int,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    """Cosine search over chunks whose document belongs to ``workspace_id`` only."""
    limit = max(1, min(int(limit), 50))
    qv = _vector_literal(query_embedding)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  c.id AS chunk_id,
                  c.chunk_index,
                  left(c.content, 8000) AS content,
                  d.id AS document_id,
                  d.title,
                  d.domain,
                  d.source_uri,
                  (c.embedding <=> %s::vector) AS distance
                FROM rag_chunks c
                JOIN rag_documents d ON d.id = c.document_id
                WHERE d.tenant_id = %s
                  AND d.user_id = %s
                  AND d.workspace_id = %s
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (qv, tenant_id, user_id, workspace_id, qv, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        dist = r.get("distance")
        out.append(
            {
                "chunk_id": r["chunk_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "document_id": r["document_id"],
                "title": r["title"],
                "domain": r["domain"],
                "source_uri": r.get("source_uri"),
                "distance": float(dist) if dist is not None else None,
            }
        )
    return out


def rag_vector_search(
    tenant_id: int,
    user_id: uuid.UUID,
    query_embedding: list[float],
    domain: str | None,
    limit: int,
    *,
    tenant_wide_domain: bool = False,
) -> list[dict[str, Any]]:
    """Cosine distance (pgvector ``<=>``); lower is more similar."""
    limit = max(1, min(int(limit), 50))
    dom = (domain or "").strip()
    dom_lc = dom.lower()
    qv = _vector_literal(query_embedding)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if tenant_wide_domain:
                if not dom_lc:
                    rows = []
                else:
                    cur.execute(
                        """
                        SELECT
                          c.id AS chunk_id,
                          c.chunk_index,
                          left(c.content, 8000) AS content,
                          d.id AS document_id,
                          d.title,
                          d.domain,
                          d.source_uri,
                          (c.embedding <=> %s::vector) AS distance
                        FROM rag_chunks c
                        JOIN rag_documents d ON d.id = c.document_id
                        WHERE d.tenant_id = %s
                          AND d.workspace_id IS NULL
                          AND lower(trim(d.domain)) = %s
                        ORDER BY c.embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (qv, tenant_id, dom_lc, qv, limit),
                    )
                    rows = cur.fetchall()
            else:
                cur.execute(
                    """
                    SELECT
                      c.id AS chunk_id,
                      c.chunk_index,
                      left(c.content, 8000) AS content,
                      d.id AS document_id,
                      d.title,
                      d.domain,
                      (c.embedding <=> %s::vector) AS distance
                    FROM rag_chunks c
                    JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.tenant_id = %s
                      AND d.user_id = %s
                      AND d.workspace_id IS NULL
                      AND (%s = '' OR d.domain = %s)
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dom, dom, qv, limit),
                )
                rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        dist = r.get("distance")
        out.append(
            {
                "chunk_id": r["chunk_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "document_id": r["document_id"],
                "title": r["title"],
                "domain": r["domain"],
                "source_uri": r.get("source_uri"),
                "distance": float(dist) if dist is not None else None,
            }
        )
    return out


