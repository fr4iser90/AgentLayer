"""Index consent tiers for workspaces (ADR 0009): none | symbols | text."""

from __future__ import annotations

from alembic import op

revision = "schema_119"
down_revision = "schema_118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS index_consent VARCHAR(16) NOT NULL DEFAULT 'text';
        """
    )
    op.execute(
        """
        UPDATE project_workspaces
           SET index_consent = 'none'
         WHERE execution_mode = 'client'
           AND index_consent IS DISTINCT FROM 'none';
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP CONSTRAINT IF EXISTS project_workspaces_index_consent_check;
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD CONSTRAINT project_workspaces_index_consent_check
            CHECK (index_consent IN ('none', 'symbols', 'text'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.index_consent IS
          'none: nothing leaves the client. symbols: name/kind/path/line/signature<=200. '
          'text: also file and document bodies for RAG/knowledge/memory. ADR 0009. '
          'Default text for server workspaces, none for client. Never implied across tiers.';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS workspace_index_consent_max VARCHAR(16) NOT NULL DEFAULT 'text';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_workspace_index_consent_max_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_workspace_index_consent_max_check
            CHECK (workspace_index_consent_max IN ('none', 'symbols', 'text'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.workspace_index_consent_max IS
          'Hard ceiling on project_workspaces.index_consent. Users cannot PATCH above this; '
          'effective consent is min(workspace, this cap). ADR 0009.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP CONSTRAINT IF EXISTS project_workspaces_index_consent_check;
        """
    )
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS index_consent;")
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_workspace_index_consent_max_check;
        """
    )
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS workspace_index_consent_max;")
