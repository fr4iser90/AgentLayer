"""scheduler_jobs.last_run_at for interval execution (server + IDE ack).

Revision ID: schema_031
Revises: schema_030
"""

from __future__ import annotations

from alembic import op

revision = "schema_031"
down_revision = "schema_030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          ADD COLUMN IF NOT EXISTS last_run_at TIMESTAMPTZ NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN scheduler_jobs.last_run_at IS
          'UTC time of last successful run (general / coding_agent) or IDE ack-run; drives next due window.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scheduler_jobs DROP COLUMN IF EXISTS last_run_at;")
