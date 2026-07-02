"""Tenant CMS review workflow (knowledge companion task 06)."""

from __future__ import annotations

from alembic import op

revision = "schema_114"
down_revision = "schema_113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenant_content DROP CONSTRAINT IF EXISTS tenant_content_status_check;
        ALTER TABLE tenant_content
          ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ NULL,
          ADD COLUMN IF NOT EXISTS approved_by_user_id UUID NULL
            REFERENCES users(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS published_by_user_id UUID NULL
            REFERENCES users(id) ON DELETE SET NULL,
          ADD COLUMN IF NOT EXISTS last_review_comment TEXT NULL;
        ALTER TABLE tenant_content
          ADD CONSTRAINT tenant_content_status_check
            CHECK (status IN (
              'draft', 'in_review', 'approved', 'published', 'deprecated', 'archived'
            ));
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_content_versions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          content_id UUID NOT NULL REFERENCES tenant_content(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          version INTEGER NOT NULL,
          title VARCHAR(512) NOT NULL,
          body_md TEXT NOT NULL,
          content_sha256 VARCHAR(64) NOT NULL,
          snapshot_reason VARCHAR(32) NOT NULL DEFAULT 'publish',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          CONSTRAINT tenant_content_versions_reason_check
            CHECK (snapshot_reason IN ('publish', 'pre_publish')),
          CONSTRAINT tenant_content_versions_version_positive CHECK (version >= 1),
          CONSTRAINT tenant_content_versions_unique UNIQUE (content_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_content_versions_content
          ON tenant_content_versions (content_id, version DESC);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_content_audit_events (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          content_id UUID NOT NULL REFERENCES tenant_content(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          event_type VARCHAR(32) NOT NULL,
          actor_user_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
          comment TEXT NULL,
          content_version INTEGER NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT tenant_content_audit_event_type_check
            CHECK (event_type IN (
              'submit', 'approve', 'reject', 'publish', 'archive', 'admin_override'
            ))
        );
        CREATE INDEX IF NOT EXISTS idx_tenant_content_audit_content
          ON tenant_content_audit_events (content_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_tenant_content_audit_tenant
          ON tenant_content_audit_events (tenant_id, event_type, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_content_audit_events;")
    op.execute("DROP TABLE IF EXISTS tenant_content_versions;")
    op.execute(
        """
        ALTER TABLE tenant_content DROP CONSTRAINT IF EXISTS tenant_content_status_check;
        ALTER TABLE tenant_content
          DROP COLUMN IF EXISTS last_review_comment,
          DROP COLUMN IF EXISTS published_by_user_id,
          DROP COLUMN IF EXISTS approved_by_user_id,
          DROP COLUMN IF EXISTS approved_at;
        UPDATE tenant_content SET status = 'draft'
          WHERE status IN ('in_review', 'approved', 'deprecated');
        ALTER TABLE tenant_content
          ADD CONSTRAINT tenant_content_status_check
            CHECK (status IN ('draft', 'published', 'archived'));
        """
    )
