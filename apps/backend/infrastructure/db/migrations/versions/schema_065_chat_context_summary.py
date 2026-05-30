"""Persisted LLM context summary for long chat conversations."""

from __future__ import annotations

from alembic import op

revision = "schema_065"
down_revision = "schema_064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS context_summary TEXT NOT NULL DEFAULT '',
          ADD COLUMN IF NOT EXISTS context_summary_message_count INT NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS context_summary_updated_at TIMESTAMPTZ NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.context_summary IS
          'LLM-generated summary of older chat turns (working context only; full history stays in chat_messages).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.context_summary_message_count IS
          'Number of user/assistant messages from the start covered by context_summary.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS context_summary_updated_at,
          DROP COLUMN IF EXISTS context_summary_message_count,
          DROP COLUMN IF EXISTS context_summary;
        """
    )
