"""Per-workspace semantic index + retrieval layer toggles and index metadata."""

from __future__ import annotations

from alembic import op

revision = "schema_053"
down_revision = "schema_052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS semantic_index_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS retrieval_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS last_index_at TIMESTAMPTZ NULL,
          ADD COLUMN IF NOT EXISTS last_index_stats JSONB NULL,
          ADD COLUMN IF NOT EXISTS last_index_error TEXT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.semantic_index_enabled IS
          'When true, coding_index may run and code_semantic uses Qdrant for this workspace.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.retrieval_enabled IS
          'When true, retrieve_context and bundled retrieval run for this workspace.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP COLUMN IF EXISTS last_index_error,
          DROP COLUMN IF EXISTS last_index_stats,
          DROP COLUMN IF EXISTS last_index_at,
          DROP COLUMN IF EXISTS retrieval_enabled,
          DROP COLUMN IF EXISTS semantic_index_enabled;
        """
    )
