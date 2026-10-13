"""schema_126: per-conversation context-inject digests (DSH-style once+change).

Revision ID: schema_126
Revises: schema_125
"""

from __future__ import annotations

from alembic import op

revision = "schema_126"
down_revision = "schema_125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS context_inject_digests JSONB NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.context_inject_digests IS
          'Per agent_id → {kind → sha256} for on-change context injects (UI + sticky skip).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          DROP COLUMN IF EXISTS context_inject_digests;
        """
    )
