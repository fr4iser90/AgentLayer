"""Operator settings: memory (facts/notes) + RAG (no env).

Revision ID: schema_021
Revises: schema_020
"""

from __future__ import annotations

from alembic import op

revision = "schema_021"
down_revision = "schema_020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS memory_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS rag_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS rag_embedding_model TEXT NOT NULL DEFAULT 'nomic-embed-text',
          ADD COLUMN IF NOT EXISTS rag_embedding_dim INTEGER NOT NULL DEFAULT 768,
          ADD COLUMN IF NOT EXISTS rag_chunk_size INTEGER NOT NULL DEFAULT 1200,
          ADD COLUMN IF NOT EXISTS rag_chunk_overlap INTEGER NOT NULL DEFAULT 200,
          ADD COLUMN IF NOT EXISTS rag_top_k INTEGER NOT NULL DEFAULT 8,
          ADD COLUMN IF NOT EXISTS rag_embed_timeout_sec DOUBLE PRECISION NOT NULL DEFAULT 120,
          ADD COLUMN IF NOT EXISTS rag_tenant_shared_domains TEXT NOT NULL DEFAULT 'agentlayer_docs',
          ADD COLUMN IF NOT EXISTS docs_root TEXT;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS docs_root,
          DROP COLUMN IF EXISTS rag_tenant_shared_domains,
          DROP COLUMN IF EXISTS rag_embed_timeout_sec,
          DROP COLUMN IF EXISTS rag_top_k,
          DROP COLUMN IF EXISTS rag_chunk_overlap,
          DROP COLUMN IF EXISTS rag_chunk_size,
          DROP COLUMN IF EXISTS rag_embedding_dim,
          DROP COLUMN IF EXISTS rag_embedding_model,
          DROP COLUMN IF EXISTS rag_enabled,
          DROP COLUMN IF EXISTS memory_enabled;
        """
    )
