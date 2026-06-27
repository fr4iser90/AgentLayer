"""Scoped agent access governance policies.

Revision ID: schema_109
Revises: schema_108
Create Date: 2026-06-27
"""

from __future__ import annotations

from alembic import op

revision = "schema_109"
down_revision = "schema_108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_access_policies (
          id BIGSERIAL PRIMARY KEY,
          scope VARCHAR(16) NOT NULL,
          tenant_id BIGINT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
          agent_id VARCHAR(64) NOT NULL,
          direct_state VARCHAR(16) NOT NULL DEFAULT 'inherit',
          delegate_state VARCHAR(16) NOT NULL DEFAULT 'inherit',
          notes TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          CONSTRAINT agent_access_policies_scope_check
            CHECK (scope IN ('global', 'tenant', 'user')),
          CONSTRAINT agent_access_policies_direct_state_check
            CHECK (direct_state IN ('inherit', 'allow', 'deny')),
          CONSTRAINT agent_access_policies_delegate_state_check
            CHECK (delegate_state IN ('inherit', 'allow', 'deny')),
          CONSTRAINT agent_access_policies_agent_id_check
            CHECK (agent_id ~ '^[a-z0-9_][a-z0-9_-]{0,63}$'),
          CONSTRAINT agent_access_policies_scope_target_check CHECK (
            (scope = 'global' AND tenant_id IS NULL AND user_id IS NULL)
            OR (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL)
            OR (scope = 'user' AND user_id IS NOT NULL)
          )
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_access_policies_global
          ON agent_access_policies (agent_id)
          WHERE scope = 'global';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_access_policies_tenant
          ON agent_access_policies (tenant_id, agent_id)
          WHERE scope = 'tenant';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_access_policies_user
          ON agent_access_policies (user_id, agent_id)
          WHERE scope = 'user';
        CREATE INDEX IF NOT EXISTS idx_agent_access_policies_tenant
          ON agent_access_policies (tenant_id, agent_id)
          WHERE scope = 'tenant';
        CREATE INDEX IF NOT EXISTS idx_agent_access_policies_user
          ON agent_access_policies (user_id, agent_id)
          WHERE scope = 'user';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_access_policies;")
