"""Add session_goal / session_todos JSONB on chat_conversations (harness state)."""

from __future__ import annotations

from alembic import op

revision = "schema_116"
down_revision = "schema_115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS session_goal JSONB NULL,
          ADD COLUMN IF NOT EXISTS session_todos JSONB NOT NULL DEFAULT '[]'::jsonb;
        COMMENT ON COLUMN chat_conversations.session_goal IS
          'Ephemeral harness goal for this chat (create_goal/update_goal); not product agent_tasks.';
        COMMENT ON COLUMN chat_conversations.session_todos IS
          'Ephemeral harness todo list (todo_write); not product agent_tasks / todos table.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS session_goal,
          DROP COLUMN IF EXISTS session_todos;
        """
    )
