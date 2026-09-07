"""Add session_plan_mode on chat_conversations."""

from __future__ import annotations

from alembic import op

revision = "schema_117"
down_revision = "schema_116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS session_plan_mode BOOLEAN NOT NULL DEFAULT false;
        COMMENT ON COLUMN chat_conversations.session_plan_mode IS
          'Soft plan-mode: when true, inject planning guidance and prefer exit_plan_mode before acting.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_conversations DROP COLUMN IF EXISTS session_plan_mode;")
