"""Workspace index policies: index_on_write, graph toggle, file state, operator defaults."""

from __future__ import annotations

from alembic import op

revision = "schema_064"
down_revision = "schema_063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS index_on_write VARCHAR(16) NULL
            CHECK (index_on_write IS NULL OR index_on_write IN ('off', 'debounced', 'immediate')),
          ADD COLUMN IF NOT EXISTS graph_index_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS retrieve_context_sources JSONB NULL;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_index_file_state (
          workspace_id UUID NOT NULL REFERENCES project_workspaces(id) ON DELETE CASCADE,
          path TEXT NOT NULL,
          content_sha256 VARCHAR(64) NOT NULL,
          indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (workspace_id, path)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workspace_index_file_state_ws
          ON workspace_index_file_state (workspace_id);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS workspace_index_on_write_default VARCHAR(16) NOT NULL DEFAULT 'debounced'
            CHECK (workspace_index_on_write_default IN ('off', 'debounced', 'immediate')),
          ADD COLUMN IF NOT EXISTS workspace_reindex_after_git_pull BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS workspace_nightly_reindex_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS workspace_nightly_reindex_enabled,
          DROP COLUMN IF EXISTS workspace_reindex_after_git_pull,
          DROP COLUMN IF EXISTS workspace_index_on_write_default;
        """
    )
    op.execute("DROP TABLE IF EXISTS workspace_index_file_state;")
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP COLUMN IF EXISTS retrieve_context_sources,
          DROP COLUMN IF EXISTS graph_index_enabled,
          DROP COLUMN IF EXISTS index_on_write;
        """
    )
