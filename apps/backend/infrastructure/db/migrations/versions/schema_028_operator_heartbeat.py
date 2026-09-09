"""Operator heartbeat: periodic agent tick (Admin → Interfaces).

Revision ID: schema_028
Revises: schema_027
"""

from __future__ import annotations

from alembic import op

revision = "schema_028"
down_revision = "schema_027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS heartbeat_enabled BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS heartbeat_interval_minutes INTEGER NOT NULL DEFAULT 60,
          ADD COLUMN IF NOT EXISTS heartbeat_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS heartbeat_model TEXT,
          ADD COLUMN IF NOT EXISTS heartbeat_max_tool_rounds INTEGER,
          ADD COLUMN IF NOT EXISTS heartbeat_notify_only_if_not_ok BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS heartbeat_max_outbound_per_day INTEGER NOT NULL DEFAULT 10,
          ADD COLUMN IF NOT EXISTS heartbeat_allowed_tool_packages TEXT,
          ADD COLUMN IF NOT EXISTS heartbeat_llm_backend TEXT NOT NULL DEFAULT 'inherit',
          ADD COLUMN IF NOT EXISTS heartbeat_tools_mode TEXT NOT NULL DEFAULT 'none',
          ADD COLUMN IF NOT EXISTS heartbeat_instructions TEXT;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS heartbeat_outbound_daily (
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          day_utc DATE NOT NULL,
          outbound_count INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY (user_id, day_utc)
        );
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.heartbeat_user_id IS
          'User identity for heartbeat tools/tenant; required for ticks when heartbeat_enabled.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS heartbeat_outbound_daily;")
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS heartbeat_instructions,
          DROP COLUMN IF EXISTS heartbeat_tools_mode,
          DROP COLUMN IF EXISTS heartbeat_llm_backend,
          DROP COLUMN IF EXISTS heartbeat_allowed_tool_packages,
          DROP COLUMN IF EXISTS heartbeat_max_outbound_per_day,
          DROP COLUMN IF EXISTS heartbeat_notify_only_if_not_ok,
          DROP COLUMN IF EXISTS heartbeat_max_tool_rounds,
          DROP COLUMN IF EXISTS heartbeat_model,
          DROP COLUMN IF EXISTS heartbeat_user_id,
          DROP COLUMN IF EXISTS heartbeat_interval_minutes,
          DROP COLUMN IF EXISTS heartbeat_enabled;
        """
    )
