"""Tenant CMS content (knowledge companion task 04)."""

from __future__ import annotations

from alembic import op

revision = "schema_112"
down_revision = "schema_111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_content (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          slug VARCHAR(128) NOT NULL,
          title VARCHAR(512) NOT NULL,
          body_md TEXT NOT NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'draft',
          source_type VARCHAR(32) NOT NULL DEFAULT 'self_authored',
          disclaimer_level VARCHAR(32) NOT NULL DEFAULT 'learning_aid',
          target_profession_roles JSONB NOT NULL DEFAULT '[]'::jsonb,
          target_departments JSONB NOT NULL DEFAULT '[]'::jsonb,
          vertical_profile VARCHAR(64) NULL,
          author_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          published_at TIMESTAMPTZ NULL,
          version INTEGER NOT NULL DEFAULT 1,
          content_sha256 VARCHAR(64) NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT tenant_content_status_check
            CHECK (status IN ('draft', 'published', 'archived')),
          CONSTRAINT tenant_content_source_type_check
            CHECK (source_type IN ('self_authored')),
          CONSTRAINT tenant_content_disclaimer_check
            CHECK (disclaimer_level IN ('learning_aid', 'local_draft', 'approved')),
          CONSTRAINT tenant_content_body_len_check
            CHECK (char_length(body_md) >= 1)
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_content_tenant_slug
          ON tenant_content (tenant_id, slug);
        CREATE INDEX IF NOT EXISTS idx_tenant_content_tenant_status
          ON tenant_content (tenant_id, status, updated_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_content;")
