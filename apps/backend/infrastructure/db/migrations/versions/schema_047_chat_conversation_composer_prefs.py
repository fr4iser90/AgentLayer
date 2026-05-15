"""Persist last chat composer agent + workspace per conversation (first-party UI).

Revision ID: schema_047
Revises: schema_046
"""

from __future__ import annotations

from alembic import op

revision = "schema_047"
down_revision = "schema_046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS pref_agent_id TEXT,
          ADD COLUMN IF NOT EXISTS pref_workspace_id UUID
            REFERENCES project_workspaces(id) ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.pref_agent_id IS
          'Last selected agent registry id in chat UI (e.g. general, coding).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN chat_conversations.pref_workspace_id IS
          'Last selected project workspace for agents that require one.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_conversations DROP COLUMN IF EXISTS pref_workspace_id;")
    op.execute("ALTER TABLE chat_conversations DROP COLUMN IF EXISTS pref_agent_id;")
