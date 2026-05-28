"""operator_settings: fingerprint for incremental RAG docs ingest."""

from __future__ import annotations

from alembic import op

revision = "schema_063"
down_revision = "schema_062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS rag_docs_ingest_fingerprint VARCHAR(128);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS rag_docs_ingest_fingerprint;
        """
    )
