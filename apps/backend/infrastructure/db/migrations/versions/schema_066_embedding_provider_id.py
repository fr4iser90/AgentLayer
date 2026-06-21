"""Add rag_embedding_provider_id for selecting active embedding catalog provider."""

from __future__ import annotations

from alembic import op

revision = "schema_066"
down_revision = "schema_065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS rag_embedding_provider_id VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.rag_embedding_provider_id IS
          'Active embedding catalog provider id (embedding_provider_1, embedding_provider_33, …).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS rag_embedding_provider_id;
        """
    )
