"""User notification channel preferences + outbound daily caps."""

from __future__ import annotations

from alembic import op

revision = "schema_076"
down_revision = "schema_075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_notification_prefs (
          user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          tenant_id INT NOT NULL,
          telegram_enabled BOOLEAN NOT NULL DEFAULT false,
          discord_enabled BOOLEAN NOT NULL DEFAULT false,
          telegram_schedules BOOLEAN NOT NULL DEFAULT true,
          telegram_dashboard BOOLEAN NOT NULL DEFAULT false,
          discord_schedules BOOLEAN NOT NULL DEFAULT true,
          discord_dashboard BOOLEAN NOT NULL DEFAULT false,
          external_failures_only BOOLEAN NOT NULL DEFAULT true,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_outbound_daily (
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          channel TEXT NOT NULL,
          day_utc DATE NOT NULL,
          outbound_count INT NOT NULL DEFAULT 0,
          PRIMARY KEY (user_id, channel, day_utc)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_outbound_daily;")
    op.execute("DROP TABLE IF EXISTS user_notification_prefs;")
