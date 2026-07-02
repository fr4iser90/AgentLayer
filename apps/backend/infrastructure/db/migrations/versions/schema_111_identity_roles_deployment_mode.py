"""Identity roles, tenant memberships, deployment mode (knowledge companion 03b)."""

from __future__ import annotations

from alembic import op

revision = "schema_111"
down_revision = "schema_110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS deployment_mode VARCHAR(32) NOT NULL DEFAULT 'multi_tenant';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_deployment_mode_check;
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_deployment_mode_check
          CHECK (deployment_mode IN ('agent_system', 'multi_tenant'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.deployment_mode IS
          'agent_system = single team (no /org UI); multi_tenant = organizations product.';
        """
    )
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS site_role VARCHAR(32) NOT NULL DEFAULT 'site_user';
        """
    )
    op.execute(
        """
        UPDATE users SET site_role = 'site_admin' WHERE role = 'admin';
        UPDATE users SET site_role = 'site_user' WHERE role <> 'admin';
        """
    )
    op.execute(
        """
        ALTER TABLE users
          DROP CONSTRAINT IF EXISTS users_site_role_check;
        ALTER TABLE users
          ADD CONSTRAINT users_site_role_check
          CHECK (site_role IN ('site_admin', 'site_user'));
        """
    )
    op.execute(
        """
        ALTER TABLE tenants
          ADD COLUMN IF NOT EXISTS setup_completed_at TIMESTAMPTZ NULL,
          ADD COLUMN IF NOT EXISTS vertical_profile VARCHAR(64) NULL;
        """
    )
    op.execute(
        """
        UPDATE tenants SET setup_completed_at = now()
        WHERE id = 1 AND setup_completed_at IS NULL
          AND EXISTS (SELECT 1 FROM users WHERE role = 'admin' LIMIT 1);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_memberships (
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          membership_role VARCHAR(32) NOT NULL DEFAULT 'tenant_member',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, tenant_id),
          CONSTRAINT tenant_memberships_role_check
            CHECK (membership_role IN ('tenant_owner', 'tenant_admin', 'tenant_member'))
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tenant_memberships_tenant
          ON tenant_memberships (tenant_id, membership_role);
        """
    )
    op.execute(
        """
        INSERT INTO tenant_memberships (user_id, tenant_id, membership_role)
        SELECT u.id, u.tenant_id,
               CASE WHEN u.role = 'admin' THEN 'tenant_owner' ELSE 'tenant_member' END
        FROM users u
        ON CONFLICT (user_id, tenant_id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_memberships;")
    op.execute(
        """
        ALTER TABLE tenants
          DROP COLUMN IF EXISTS vertical_profile,
          DROP COLUMN IF EXISTS setup_completed_at;
        """
    )
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_site_role_check;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS site_role;")
    op.execute("ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_deployment_mode_check;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS deployment_mode;")
