"""operator_settings: embedding API key and header name (admin UI, like external LLM endpoints)."""

from __future__ import annotations

from alembic import op

revision = "schema_061"
down_revision = "schema_060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS embedding_api_key TEXT,
          ADD COLUMN IF NOT EXISTS embedding_api_header_name VARCHAR(128);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS embedding_api_key,
          DROP COLUMN IF EXISTS embedding_api_header_name;
        """
    )
