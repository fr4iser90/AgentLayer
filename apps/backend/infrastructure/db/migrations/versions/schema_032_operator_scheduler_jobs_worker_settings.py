"""operator_settings: scheduler_jobs worker toggles (Web UI, not .env).

Revision ID: schema_032
Revises: schema_031
"""

from __future__ import annotations

from alembic import op

revision = "schema_032"
down_revision = "schema_031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS scheduler_jobs_worker_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS scheduler_jobs_ide_pidea_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS scheduler_jobs_ide_pidea_timeout_sec DOUBLE PRECISION NOT NULL DEFAULT 300;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.scheduler_jobs_worker_enabled IS
          'Background thread: run persisted scheduler_jobs (general + coding_agent).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS scheduler_jobs_ide_pidea_timeout_sec,
          DROP COLUMN IF EXISTS scheduler_jobs_ide_pidea_enabled,
          DROP COLUMN IF EXISTS scheduler_jobs_worker_enabled;
        """
    )
