"""schema_127: external agent runtime binding per conversation.

Agents that declare ``external_runtime`` (e.g. ``coding_qwen``) run their turn in an
external process which keeps its own session (Qwen Code: ``qwen --resume <id>``). One
conversation maps to one vendor session, so the native id is stored on the conversation
and reused on the next turn.

Revision ID: schema_127
Revises: schema_126
"""

from __future__ import annotations

from alembic import op

revision = "schema_127"
down_revision = "schema_126"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS external_runtime TEXT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS external_session_id TEXT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.external_runtime IS
          'Runtime id from agent.yaml (external_runtime) once this conversation ran outside AgentLayer.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.external_session_id IS
          'Vendor-native session id used to resume the same external session on the next turn.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS external_session_id;
        """
    )
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS external_runtime;
        """
    )
