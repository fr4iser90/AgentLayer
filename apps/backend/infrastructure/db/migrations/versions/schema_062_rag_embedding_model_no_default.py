"""RAG embedding model: no hardcoded default (empty until provider sync or Admin)."""

from __future__ import annotations

from alembic import op

revision = "schema_062"
down_revision = "schema_061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN rag_embedding_model SET DEFAULT '';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN rag_embedding_model SET DEFAULT 'nomic-embed-text';
        """
    )
