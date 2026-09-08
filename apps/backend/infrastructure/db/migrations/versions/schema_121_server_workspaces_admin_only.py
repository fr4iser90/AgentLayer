"""schema_121: server workspaces admin-only by default (ADR 0009)."""

from __future__ import annotations

from alembic import op

revision = "schema_121"
down_revision = "schema_120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS server_workspaces_admin_only BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.server_workspaces_admin_only IS
          'When true (default), only users with role=admin may create/bind/use '
          'execution_mode=server workspaces (hosted coding). Other users are client-only.';
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE operator_settings DROP COLUMN IF EXISTS server_workspaces_admin_only;"
    )
