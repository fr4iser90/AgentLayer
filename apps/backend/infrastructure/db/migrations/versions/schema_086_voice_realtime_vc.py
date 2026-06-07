"""Voice phase C: realtime WebSocket + Discord voice channel flags.

Revision ID: schema_086
Revises: schema_085
"""

from __future__ import annotations

from alembic import op

revision = "schema_086"
down_revision = "schema_085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_realtime_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          voice_discord_vc_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS voice_discord_vc_enabled;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS voice_realtime_enabled;")
