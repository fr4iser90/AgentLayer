"""Add tenant_id to project_workspaces so admin surfaces can scope by tenant.

Before this revision the tenant of a workspace could only be inferred by joining
``owner_user_id`` to ``users.tenant_id``. Every admin surface that needed the
answer had to do that join itself, and one of them
(``fetch_editable_workspace_tenant_name``) selected a column that did not exist.

The column is backfilled from the owner's home tenant. ``users.tenant_id`` is
NOT NULL and ``owner_user_id`` is a NOT NULL FK to ``users``, so the backfill
resolves for every row; the NOT NULL constraint is applied only afterwards so
the FK validation never sees a NULL.
"""

from __future__ import annotations

from alembic import op

revision = "schema_132"
down_revision = "schema_131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS tenant_id BIGINT;
        """
    )
    op.execute(
        """
        UPDATE project_workspaces w
          SET tenant_id = u.tenant_id
          FROM users u
          WHERE u.id = w.owner_user_id
            AND w.tenant_id IS NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          ALTER COLUMN tenant_id SET NOT NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE project_workspaces
          ADD CONSTRAINT project_workspaces_tenant_id_fkey
          FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_project_workspaces_tenant
          ON project_workspaces (tenant_id);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN project_workspaces.tenant_id IS
          'Home tenant of the workspace, backfilled from owner_user_id at creation '
          'time. Kept in step with the owner by move_user_tenant(); do not set it '
          'independently of the owner.';
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_project_workspaces_tenant;")
    op.execute(
        """
        ALTER TABLE project_workspaces
          DROP CONSTRAINT IF EXISTS project_workspaces_tenant_id_fkey;
        """
    )
    op.execute("ALTER TABLE project_workspaces DROP COLUMN IF EXISTS tenant_id;")
