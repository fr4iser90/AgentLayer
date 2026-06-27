"""Scoped model and provider capability access policies.

Revision ID: schema_105
Revises: schema_104
Create Date: 2026-06-26
"""

from __future__ import annotations

from alembic import op

revision = "schema_105"
down_revision = "schema_104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_access_policies (
          id BIGSERIAL PRIMARY KEY,
          scope VARCHAR(16) NOT NULL,
          tenant_id BIGINT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
          provider_id VARCHAR(64) NOT NULL,
          model_id TEXT NOT NULL,
          access_state VARCHAR(16) NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT model_access_policies_scope_check
            CHECK (scope IN ('global', 'tenant', 'user')),
          CONSTRAINT model_access_policies_state_check
            CHECK (access_state IN ('inherit', 'allow', 'deny')),
          CONSTRAINT model_access_policies_provider_id_check
            CHECK (provider_id ~ '^[a-z0-9_-]{1,64}$'),
          CONSTRAINT model_access_policies_scope_target_check CHECK (
            (scope = 'global' AND tenant_id IS NULL AND user_id IS NULL)
            OR (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL)
            OR (scope = 'user' AND user_id IS NOT NULL)
          )
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_access_policies_global
          ON model_access_policies (provider_id, model_id)
          WHERE scope = 'global';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_access_policies_tenant
          ON model_access_policies (tenant_id, provider_id, model_id)
          WHERE scope = 'tenant';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_access_policies_user
          ON model_access_policies (user_id, provider_id, model_id)
          WHERE scope = 'user';
        CREATE INDEX IF NOT EXISTS idx_model_access_policies_tenant
          ON model_access_policies (tenant_id, provider_id, model_id)
          WHERE scope = 'tenant';
        CREATE INDEX IF NOT EXISTS idx_model_access_policies_user
          ON model_access_policies (user_id, provider_id, model_id)
          WHERE scope = 'user';
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS model_default_policies (
          id BIGSERIAL PRIMARY KEY,
          scope VARCHAR(16) NOT NULL,
          tenant_id BIGINT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
          profile VARCHAR(16) NOT NULL,
          provider_id VARCHAR(64) NOT NULL,
          model_id TEXT NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT model_default_policies_scope_check
            CHECK (scope IN ('global', 'tenant', 'user')),
          CONSTRAINT model_default_policies_profile_check
            CHECK (profile IN ('default', 'agent', 'coding', 'vlm', 'embedding', 'extractor', 'stt', 'tts')),
          CONSTRAINT model_default_policies_provider_id_check
            CHECK (provider_id ~ '^[a-z0-9_-]{1,64}$'),
          CONSTRAINT model_default_policies_scope_target_check CHECK (
            (scope = 'global' AND tenant_id IS NULL AND user_id IS NULL)
            OR (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL)
            OR (scope = 'user' AND user_id IS NOT NULL)
          )
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_default_policies_global
          ON model_default_policies (profile)
          WHERE scope = 'global';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_default_policies_tenant
          ON model_default_policies (tenant_id, profile)
          WHERE scope = 'tenant';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_default_policies_user
          ON model_default_policies (user_id, profile)
          WHERE scope = 'user';
        CREATE INDEX IF NOT EXISTS idx_model_default_policies_tenant
          ON model_default_policies (tenant_id)
          WHERE scope = 'tenant';
        CREATE INDEX IF NOT EXISTS idx_model_default_policies_user
          ON model_default_policies (user_id)
          WHERE scope = 'user';
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_capability_policies (
          id BIGSERIAL PRIMARY KEY,
          scope VARCHAR(16) NOT NULL,
          tenant_id BIGINT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NULL REFERENCES users(id) ON DELETE CASCADE,
          capability VARCHAR(32) NOT NULL,
          provider_id VARCHAR(64) NOT NULL,
          access_state VARCHAR(16) NOT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT provider_capability_policies_scope_check
            CHECK (scope IN ('global', 'tenant', 'user')),
          CONSTRAINT provider_capability_policies_capability_check
            CHECK (capability IN ('chat', 'embedding', 'extractor', 'stt', 'tts', 'voice_realtime')),
          CONSTRAINT provider_capability_policies_state_check
            CHECK (access_state IN ('inherit', 'allow', 'deny')),
          CONSTRAINT provider_capability_policies_provider_id_check
            CHECK (provider_id ~ '^[a-z0-9_-]{1,64}$'),
          CONSTRAINT provider_capability_policies_scope_target_check CHECK (
            (scope = 'global' AND tenant_id IS NULL AND user_id IS NULL)
            OR (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL)
            OR (scope = 'user' AND user_id IS NOT NULL)
          )
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_capability_policies_global
          ON provider_capability_policies (capability, provider_id)
          WHERE scope = 'global';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_capability_policies_tenant
          ON provider_capability_policies (tenant_id, capability, provider_id)
          WHERE scope = 'tenant';
        CREATE UNIQUE INDEX IF NOT EXISTS uq_provider_capability_policies_user
          ON provider_capability_policies (user_id, capability, provider_id)
          WHERE scope = 'user';
        CREATE INDEX IF NOT EXISTS idx_provider_capability_policies_tenant
          ON provider_capability_policies (tenant_id, capability, provider_id)
          WHERE scope = 'tenant';
        CREATE INDEX IF NOT EXISTS idx_provider_capability_policies_user
          ON provider_capability_policies (user_id, capability, provider_id)
          WHERE scope = 'user';
        """
    )
    op.execute(
        """
        INSERT INTO model_access_policies (
          scope, tenant_id, user_id, provider_id, model_id, access_state, sort_order, updated_at
        )
        SELECT
          'global',
          NULL,
          NULL,
          provider_id,
          model_id,
          CASE WHEN visible_in_chat THEN 'allow' ELSE 'deny' END,
          sort_order,
          updated_at
        FROM operator_model_catalog_prefs
        ON CONFLICT DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS provider_capability_policies;")
    op.execute("DROP TABLE IF EXISTS model_default_policies;")
    op.execute("DROP TABLE IF EXISTS model_access_policies;")
