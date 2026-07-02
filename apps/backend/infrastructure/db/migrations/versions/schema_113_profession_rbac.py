"""Profession RBAC tables (knowledge companion task 05)."""

from __future__ import annotations

from alembic import op

revision = "schema_113"
down_revision = "schema_112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_departments (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          slug VARCHAR(64) NOT NULL,
          name VARCHAR(256) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT tenant_departments_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_departments_slug
          ON tenant_departments (tenant_id, slug);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_profession_roles (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          slug VARCHAR(64) NOT NULL,
          name VARCHAR(256) NOT NULL,
          role_kind VARCHAR(32) NOT NULL DEFAULT 'end_user',
          content_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT tenant_profession_roles_slug_check CHECK (slug ~ '^[a-z0-9][a-z0-9_-]{0,62}$'),
          CONSTRAINT tenant_profession_roles_kind_check
            CHECK (role_kind IN (
              'content_editor', 'content_reviewer', 'content_approver',
              'domain_admin', 'end_user', 'trainee'
            ))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_profession_roles_slug
          ON tenant_profession_roles (tenant_id, slug);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profession_assignments (
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          profession_role_id UUID NOT NULL REFERENCES tenant_profession_roles(id) ON DELETE RESTRICT,
          department_id UUID NULL REFERENCES tenant_departments(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (user_id, tenant_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_profession_assignments_role
          ON user_profession_assignments (tenant_id, profession_role_id);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_qualifications (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          qualification_type VARCHAR(64) NOT NULL,
          valid_until DATE NULL,
          evidence_ref VARCHAR(512) NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT user_qualifications_type_check
            CHECK (qualification_type ~ '^[a-z0-9][a-z0-9_-]{0,62}$')
        );
        CREATE INDEX IF NOT EXISTS idx_user_qualifications_user
          ON user_qualifications (tenant_id, user_id, qualification_type);
        """
    )
    op.execute(
        """
        ALTER TABLE tenant_content
          ADD COLUMN IF NOT EXISTS required_qualifications JSONB NOT NULL DEFAULT '[]'::jsonb,
          ADD COLUMN IF NOT EXISTS content_category VARCHAR(64) NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenant_content
          DROP COLUMN IF EXISTS content_category,
          DROP COLUMN IF EXISTS required_qualifications;
        """
    )
    op.execute("DROP TABLE IF EXISTS user_qualifications;")
    op.execute("DROP TABLE IF EXISTS user_profession_assignments;")
    op.execute("DROP TABLE IF EXISTS tenant_profession_roles;")
    op.execute("DROP TABLE IF EXISTS tenant_departments;")
