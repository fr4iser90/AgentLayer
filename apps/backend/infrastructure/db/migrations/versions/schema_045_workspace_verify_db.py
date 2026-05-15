"""Workspace verify policy + persisted verify runs (DB, not repo JSON).

Revision ID: schema_045
Revises: schema_044
"""

from __future__ import annotations

from alembic import op

revision = "schema_045"
down_revision = "schema_044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS verify_command TEXT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS verify_required BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.verify_command IS
          'Optional shell command run only via coding_workspace_verify (same safety as coding_bash).';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.verify_required IS
          'When true, chat_completion requires a successful coding_workspace_verify before final text (coding agent).';
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_verify_runs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          workspace_id UUID NOT NULL REFERENCES project_workspaces(id) ON DELETE CASCADE,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          agent_run_id TEXT NULL,
          command TEXT NOT NULL,
          exit_code INT NOT NULL,
          ok BOOLEAN NOT NULL,
          output_preview TEXT NULL,
          error_message TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_verify_runs_ws_created "
        "ON workspace_verify_runs(workspace_id, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_verify_runs;")
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS verify_required;")
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS verify_command;")
