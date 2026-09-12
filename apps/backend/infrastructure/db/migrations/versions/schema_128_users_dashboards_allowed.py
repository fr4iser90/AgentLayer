"""schema_128: users.dashboards_allowed + users.dashboard_quota — dashboards default enabled + per-user grant/quota.

Per the roles/agent-assignment roadmap (P4): dashboards are so regulable as workspaces.
``dashboards_allowed`` defaults true (preserves auto-create for every new user); admins and
site_admins always may. ``dashboard_quota`` defaults to 1 and caps how many dashboards a user
may keep.
"""

from __future__ import annotations

from alembic import op

revision = "schema_128"
down_revision = "schema_127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS dashboards_allowed BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN users.dashboards_allowed IS
          'When true, non-admin users may create/keep dashboards (default true = dashboards enabled). '
          'Admins and site_admins always may.';
        """
    )
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS dashboard_quota INTEGER NOT NULL DEFAULT 1;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN users.dashboard_quota IS
          'Maximum number of dashboards a user may keep (default 1). Enforced on create and list.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS dashboard_quota;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS dashboards_allowed;")
