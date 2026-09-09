"""schema_123: chat_messages client_id/reasoning + chat storage quotas on operator_settings."""

from __future__ import annotations

from alembic import op

revision = "schema_123"
down_revision = "schema_122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_messages
          ADD COLUMN IF NOT EXISTS client_message_id TEXT NULL,
          ADD COLUMN IF NOT EXISTS reasoning TEXT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_messages.client_message_id IS
          'Stable client/UI message id (UUID string). Links agent_log turnLogs to user rows.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_messages.reasoning IS
          'Optional model reasoning/thinking text for assistant messages.';
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_msg_client_id
          ON chat_messages (conversation_id, client_message_id)
          WHERE client_message_id IS NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS chat_max_conversation_mb INTEGER NOT NULL DEFAULT 2048,
          ADD COLUMN IF NOT EXISTS chat_max_personal_sessions INTEGER NOT NULL DEFAULT 100,
          ADD COLUMN IF NOT EXISTS chat_max_dashboard_sessions INTEGER NOT NULL DEFAULT 30;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.chat_max_conversation_mb IS
          'Max stored size per conversation (messages + agent_log), in megabytes. Default 2048.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.chat_max_personal_sessions IS
          'Max personal chat conversations per user (dashboard_id IS NULL).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.chat_max_dashboard_sessions IS
          'Max chat conversations per dashboard (shared + personal-dashboard threads).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS chat_max_dashboard_sessions,
          DROP COLUMN IF EXISTS chat_max_personal_sessions,
          DROP COLUMN IF EXISTS chat_max_conversation_mb;
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_chat_msg_client_id;")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS reasoning;")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS client_message_id;")
