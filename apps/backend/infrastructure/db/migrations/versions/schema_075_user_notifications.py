"""In-app user notifications (scheduler jobs, dashboard agent updates)."""

from __future__ import annotations

from alembic import op

revision = "schema_075"
down_revision = "schema_074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_notifications (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INT NOT NULL,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,
          severity TEXT NOT NULL DEFAULT 'info',
          title TEXT NOT NULL,
          body TEXT NOT NULL DEFAULT '',
          link_path TEXT NULL,
          source_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
          read_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_notifications_user_unread
          ON user_notifications (user_id, read_at, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_notifications_user_dashboard
          ON user_notifications (user_id, ((source_ref->>'dashboard_id')))
          WHERE read_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_notifications;")
