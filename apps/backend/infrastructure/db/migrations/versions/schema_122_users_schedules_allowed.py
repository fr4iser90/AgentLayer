"""schema_122: users.schedules_allowed — schedules default admin-only + per-user grant."""

from __future__ import annotations

from alembic import op

revision = "schema_122"
down_revision = "schema_121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS schedules_allowed BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN users.schedules_allowed IS
          'When true, non-admin users may create/manage scheduler_jobs (user schedules). '
          'Admins and site_admins always may. Default false = schedules are admin-only.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS schedules_allowed;")
