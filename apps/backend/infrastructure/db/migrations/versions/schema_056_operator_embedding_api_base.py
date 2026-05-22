"""operator_settings: optional embedding API base (wizard / Ollama opt-in)."""

from __future__ import annotations

from alembic import op

revision = "schema_056"
down_revision = "schema_055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS embedding_api_base_url VARCHAR(2048);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS embedding_api_base_url;
        """
    )
