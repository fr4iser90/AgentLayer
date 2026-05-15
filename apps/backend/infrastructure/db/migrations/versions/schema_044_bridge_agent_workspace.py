"""bridge_agent_sessions: optional workspace + default agent for Discord/Telegram.

Revision ID: schema_044
Revises: schema_043
"""

from __future__ import annotations

from alembic import op

revision = "schema_044"
down_revision = "schema_043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bridge_agent_sessions
          ADD COLUMN IF NOT EXISTS workspace_id UUID NULL
            REFERENCES project_workspaces(id) ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE bridge_agent_sessions
          ADD COLUMN IF NOT EXISTS default_agent_id VARCHAR(64) NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN bridge_agent_sessions.workspace_id IS
          'Optional project workspace for bridge chat_completion (coding/security tools).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN bridge_agent_sessions.default_agent_id IS
          'Optional agent_id override; if null and workspace_id set, bridges may default to coding.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bridge_agent_sessions DROP COLUMN IF EXISTS default_agent_id;")
    op.execute("ALTER TABLE bridge_agent_sessions DROP COLUMN IF EXISTS workspace_id;")
