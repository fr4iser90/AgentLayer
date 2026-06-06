"""Align pgvector ``vector(N)`` column width with ``rag_embedding_dim`` (runtime model probe)."""

from __future__ import annotations

import logging
import re
from typing import Any

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)

_VECTOR_TYPE_RE = re.compile(r"^vector\((\d+)\)$")

# Tables that store embedding vectors for RAG / memory (must share one deployment dim).
_PGVECTOR_TARGETS: tuple[dict[str, Any], ...] = (
    {
        "table": "rag_chunks",
        "column": "embedding",
        "index": "idx_rag_chunks_embedding",
        "index_where": None,
        "purge_sql": (
            "DELETE FROM rag_chunks;",
            "DELETE FROM rag_documents;",
        ),
    },
    {
        "table": "user_memory_notes",
        "column": "embedding",
        "index": "idx_user_memory_notes_embedding",
        "index_where": "WHERE deleted_at IS NULL",
        "purge_sql": ("DELETE FROM user_memory_notes;",),
    },
    {
        "table": "user_memory_graph_nodes",
        "column": "embedding",
        "index": "idx_user_memory_graph_nodes_embedding",
        "index_where": "WHERE deleted_at IS NULL AND embedding IS NOT NULL",
        "purge_sql": (
            "UPDATE user_memory_graph_nodes SET embedding = NULL WHERE embedding IS NOT NULL;",
        ),
    },
)


def read_pgvector_column_dim(*, table: str, column: str = "embedding") -> int | None:
    """Return ``N`` from ``vector(N)`` for a public schema column, or ``None`` if missing."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT format_type(a.atttypid, a.atttypmod)
                FROM pg_attribute a
                JOIN pg_class c ON c.oid = a.attrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = %s AND a.attname = %s AND n.nspname = 'public'
                """,
                (table, column),
            )
            row = cur.fetchone()
    if not row or not row[0]:
        return None
    m = _VECTOR_TYPE_RE.match(str(row[0]).strip())
    return int(m.group(1)) if m else None


def deployment_pgvector_embedding_dim() -> int | None:
    """Canonical pgvector width for this deployment (from ``rag_chunks.embedding``)."""
    return read_pgvector_column_dim(table="rag_chunks", column="embedding")


def ensure_pgvector_embedding_dim(
    target_dim: int,
    *,
    log_prefix: str = "pgvector_embedding_dim",
) -> dict[str, Any]:
    """
    Migrate all embedding pgvector columns to ``vector(target_dim)`` when needed.

    Purges stored vectors (RAG chunks/docs, memory notes; graph node embeddings nulled)
    because existing vectors are incompatible across dimensions.
    """
    dim = int(target_dim)
    if dim < 32 or dim > 4096:
        raise ValueError(f"target_dim must be 32..4096, got {dim}")

    current = deployment_pgvector_embedding_dim()
    summary: dict[str, Any] = {
        "ok": True,
        "migrated": False,
        "current_dim": current,
        "target_dim": dim,
        "tables": [t["table"] for t in _PGVECTOR_TARGETS],
    }
    if current is None:
        summary["ok"] = False
        summary["note"] = "rag_chunks.embedding column not found"
        logger.warning("%s: %s", log_prefix, summary["note"])
        return summary
    if current == dim:
        summary["note"] = "pgvector columns already match target dim"
        return summary

    logger.info(
        "%s: migrating pgvector columns %s -> %s (stored vectors will be purged)",
        log_prefix,
        current,
        dim,
    )

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            for spec in _PGVECTOR_TARGETS:
                table = spec["table"]
                column = spec["column"]
                index = spec["index"]
                index_where = spec["index_where"] or ""

                cur.execute(f"DROP INDEX IF EXISTS {index};")
                for stmt in spec["purge_sql"]:
                    cur.execute(stmt)
                cur.execute(
                    f"ALTER TABLE {table} ALTER COLUMN {column} TYPE vector({dim});"
                )
                cur.execute(
                    f"""
                    CREATE INDEX {index}
                      ON {table} USING hnsw ({column} vector_cosine_ops)
                      {index_where};
                    """
                )
        conn.commit()

    try:
        from apps.backend.infrastructure.operator_settings import set_rag_docs_ingest_fingerprint

        set_rag_docs_ingest_fingerprint("")
    except Exception:
        pass

    try:
        from apps.backend.infrastructure.operator_settings import _invalidate_pgvector_dim_cache

        _invalidate_pgvector_dim_cache()
    except Exception:
        pass

    summary["migrated"] = True
    summary["note"] = "pgvector columns migrated; re-ingest RAG docs and memory recommended"
    logger.info("%s: migration complete (%s -> %s)", log_prefix, current, dim)
    return summary
