"""User Delegate + Workspace Delegate tables."""

from __future__ import annotations

from alembic import op

revision = "schema_067"
down_revision = "schema_066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_delegate (
          user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          config JSONB NOT NULL DEFAULT '{}'::jsonb,
          notes TEXT NOT NULL DEFAULT '',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_delegate_tenant
          ON user_delegate (tenant_id);
        """
    )
    op.execute(
        """
        COMMENT ON TABLE user_delegate IS
          'Global Stellvertreter / User Delegate: explicit goals and autonomy bounds for delegated decisions.';
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_delegate (
          workspace_id UUID PRIMARY KEY REFERENCES project_workspaces(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          config JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workspace_delegate_tenant
          ON workspace_delegate (tenant_id);
        """
    )
    op.execute(
        """
        COMMENT ON TABLE workspace_delegate IS
          'Per-workspace delegate overlay; merges over user_delegate for the same keys.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_delegate;")
    op.execute("DROP TABLE IF EXISTS user_delegate;")
