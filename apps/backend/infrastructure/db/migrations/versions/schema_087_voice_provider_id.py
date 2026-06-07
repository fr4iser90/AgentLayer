"""Add voice_provider_id for selecting active voice catalog provider."""

from __future__ import annotations

from alembic import op

revision = "schema_087"
down_revision = "schema_086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS voice_provider_id VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.voice_provider_id IS
          'Active voice catalog provider id (voice_provider_1, voice_admin, …).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS voice_provider_id;
        """
    )
