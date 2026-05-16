"""Expand pgvector embedding columns to 1024 (e.g. bge-m3). Purges stored vectors — re-ingest RAG docs after upgrade.

Revision ID: schema_050
Revises: schema_049
"""

from __future__ import annotations

from alembic import op

revision = "schema_050"
down_revision = "schema_049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rag_chunks_embedding;")
    op.execute("DELETE FROM rag_chunks;")
    op.execute("DELETE FROM rag_documents;")
    op.execute("ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE vector(1024);")
    op.execute(
        """
        CREATE INDEX idx_rag_chunks_embedding
          ON rag_chunks USING hnsw (embedding vector_cosine_ops);
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_user_memory_notes_embedding;")
    op.execute("DELETE FROM user_memory_notes;")
    op.execute("ALTER TABLE user_memory_notes ALTER COLUMN embedding TYPE vector(1024);")
    op.execute(
        """
        CREATE INDEX idx_user_memory_notes_embedding
          ON user_memory_notes USING hnsw (embedding vector_cosine_ops)
          WHERE deleted_at IS NULL;
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_user_memory_graph_nodes_embedding;")
    op.execute("UPDATE user_memory_graph_nodes SET embedding = NULL WHERE embedding IS NOT NULL;")
    op.execute(
        """
        ALTER TABLE user_memory_graph_nodes
          ALTER COLUMN embedding TYPE vector(1024);
        """
    )
    op.execute(
        """
        CREATE INDEX idx_user_memory_graph_nodes_embedding
          ON user_memory_graph_nodes USING hnsw (embedding vector_cosine_ops)
          WHERE deleted_at IS NULL AND embedding IS NOT NULL;
        """
    )

    op.execute(
        """
        UPDATE operator_settings
        SET rag_embedding_dim = 1024, updated_at = now()
        WHERE id = 1 AND rag_embedding_dim < 1024;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rag_chunks_embedding;")
    op.execute("DELETE FROM rag_chunks;")
    op.execute("DELETE FROM rag_documents;")
    op.execute("ALTER TABLE rag_chunks ALTER COLUMN embedding TYPE vector(768);")
    op.execute(
        """
        CREATE INDEX idx_rag_chunks_embedding
          ON rag_chunks USING hnsw (embedding vector_cosine_ops);
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_user_memory_notes_embedding;")
    op.execute("DELETE FROM user_memory_notes;")
    op.execute("ALTER TABLE user_memory_notes ALTER COLUMN embedding TYPE vector(768);")
    op.execute(
        """
        CREATE INDEX idx_user_memory_notes_embedding
          ON user_memory_notes USING hnsw (embedding vector_cosine_ops)
          WHERE deleted_at IS NULL;
        """
    )

    op.execute("DROP INDEX IF EXISTS idx_user_memory_graph_nodes_embedding;")
    op.execute("UPDATE user_memory_graph_nodes SET embedding = NULL WHERE embedding IS NOT NULL;")
    op.execute(
        """
        ALTER TABLE user_memory_graph_nodes
          ALTER COLUMN embedding TYPE vector(768);
        """
    )
    op.execute(
        """
        CREATE INDEX idx_user_memory_graph_nodes_embedding
          ON user_memory_graph_nodes USING hnsw (embedding vector_cosine_ops)
          WHERE deleted_at IS NULL AND embedding IS NOT NULL;
        """
    )
