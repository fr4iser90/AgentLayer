"""Per-workspace MCP stdio server definitions (JSONB on project_workspaces).

Revision ID: schema_046
Revises: schema_045
"""

from __future__ import annotations

from alembic import op

revision = "schema_046"
down_revision = "schema_045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS mcp_stdio_servers_json JSONB NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.mcp_stdio_servers_json IS
          'Optional JSON array of MCP stdio servers for this workspace only; when non-empty, replaces global AGENT_MCP_* for chat in this workspace.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS mcp_stdio_servers_json;")
