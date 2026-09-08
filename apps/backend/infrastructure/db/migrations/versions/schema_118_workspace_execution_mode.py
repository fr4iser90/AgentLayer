"""Workspace execution mode: server-side tools (default) vs client-side tools (ADR 0009)."""

from __future__ import annotations

from alembic import op

revision = "schema_118"
down_revision = "schema_117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS execution_mode VARCHAR(16) NOT NULL DEFAULT 'server'
            CHECK (execution_mode IN ('server', 'client'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.execution_mode IS
          'server: files live under AGENTLAYER_WORKSPACE_PATH and tools run in the backend. '
          'client: path is on the connected client machine and the backend must never open it; '
          'see ADR 0009. Fixed at creation, because flipping it would invalidate every index '
          'and citation attached to the row.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS execution_mode;")
