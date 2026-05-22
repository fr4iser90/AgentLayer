"""Workspace-scoped doc RAG: rag_documents.workspace_id + per-workspace index metadata.

Revision ID: schema_058
Revises: schema_057
"""

from __future__ import annotations

from alembic import op

revision = "schema_058"
down_revision = "schema_057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE rag_documents
          ADD COLUMN IF NOT EXISTS workspace_id UUID NULL
            REFERENCES project_workspaces(id) ON DELETE CASCADE;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_rag_documents_workspace
          ON rag_documents (tenant_id, workspace_id)
          WHERE workspace_id IS NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS docs_rag_enabled BOOLEAN NOT NULL DEFAULT true,
          ADD COLUMN IF NOT EXISTS last_docs_rag_at TIMESTAMPTZ NULL,
          ADD COLUMN IF NOT EXISTS last_docs_rag_stats JSONB NULL,
          ADD COLUMN IF NOT EXISTS last_docs_rag_error TEXT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.docs_rag_enabled IS
          'When true, workspace index ingests *.md into pgvector scoped to this workspace.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP COLUMN IF EXISTS last_docs_rag_error,
          DROP COLUMN IF EXISTS last_docs_rag_stats,
          DROP COLUMN IF EXISTS last_docs_rag_at,
          DROP COLUMN IF EXISTS docs_rag_enabled;
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_rag_documents_workspace;")
    op.execute("ALTER TABLE rag_documents DROP COLUMN IF EXISTS workspace_id;")
