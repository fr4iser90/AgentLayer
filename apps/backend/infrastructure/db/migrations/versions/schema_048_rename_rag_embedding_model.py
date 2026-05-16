"""Rename rag_ollama_model → rag_embedding_model (RAG uses EMBEDDING_*, not Ollama).

Revision ID: schema_048
Revises: schema_047
"""

from __future__ import annotations

from alembic import op

revision = "schema_048"
down_revision = "schema_047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          RENAME COLUMN rag_ollama_model TO rag_embedding_model;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          RENAME COLUMN rag_embedding_model TO rag_ollama_model;
        """
    )
