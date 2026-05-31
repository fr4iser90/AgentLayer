"""Chat message feedback, delegate auto-respond prefs, delegate_runs audit, index-on-attach operator flag."""

from __future__ import annotations

from alembic import op

revision = "schema_070"
down_revision = "schema_069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_message_feedback (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INT NOT NULL,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
          message_position INT NOT NULL CHECK (message_position >= 0),
          rating SMALLINT NOT NULL CHECK (rating IN (-1, 1)),
          comment TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (user_id, conversation_id, message_position)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_message_feedback_conv
          ON chat_message_feedback (conversation_id, message_position);
        """
    )
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS delegate_auto_respond_enabled BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS delegate_auto_respond_after_sec INT NOT NULL DEFAULT 60
            CHECK (delegate_auto_respond_after_sec BETWEEN 15 AND 600),
          ADD COLUMN IF NOT EXISTS delegate_max_chain_turns INT NOT NULL DEFAULT 3
            CHECK (delegate_max_chain_turns BETWEEN 1 AND 10);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS delegate_runs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INT NOT NULL,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
          trigger TEXT NOT NULL DEFAULT 'idle',
          decision_summary TEXT NOT NULL DEFAULT '',
          synthetic_user_message TEXT NOT NULL DEFAULT '',
          agent_run_id UUID NULL,
          outcome TEXT NOT NULL DEFAULT 'started',
          chain_index INT NOT NULL DEFAULT 0,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_delegate_runs_user_created
          ON delegate_runs (user_id, created_at DESC);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS workspace_index_on_attach_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE operator_settings DROP COLUMN IF EXISTS workspace_index_on_attach_enabled;"
    )
    op.execute("DROP TABLE IF EXISTS delegate_runs;")
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS delegate_max_chain_turns,
          DROP COLUMN IF EXISTS delegate_auto_respond_after_sec,
          DROP COLUMN IF EXISTS delegate_auto_respond_enabled;
        """
    )
    op.execute("DROP TABLE IF EXISTS chat_message_feedback;")
