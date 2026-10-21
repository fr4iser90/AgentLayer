"""scheduler_jobs: per-job notify_on / channels / include_output."""

from __future__ import annotations

from alembic import op

revision = "schema_142"
down_revision = "schema_141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          ADD COLUMN IF NOT EXISTS notify_on TEXT NOT NULL DEFAULT 'always',
          ADD COLUMN IF NOT EXISTS notify_channels JSONB NOT NULL DEFAULT '["in_app"]'::jsonb,
          ADD COLUMN IF NOT EXISTS notify_include_output BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          DROP CONSTRAINT IF EXISTS scheduler_jobs_notify_on_check;
        """
    )
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_notify_on_check
          CHECK (notify_on IN ('never', 'failure', 'always'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN scheduler_jobs.notify_on IS
          'When to notify: never | failure | always (default always preserves prior in-app behavior).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN scheduler_jobs.notify_channels IS
          'JSON array of channels: in_app, telegram, discord.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN scheduler_jobs.notify_include_output IS
          'When true, append a short run output excerpt to the notification body.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          DROP CONSTRAINT IF EXISTS scheduler_jobs_notify_on_check;
        """
    )
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          DROP COLUMN IF EXISTS notify_include_output,
          DROP COLUMN IF EXISTS notify_channels,
          DROP COLUMN IF EXISTS notify_on;
        """
    )
