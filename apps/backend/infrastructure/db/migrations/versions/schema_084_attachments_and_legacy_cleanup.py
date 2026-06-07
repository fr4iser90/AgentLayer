"""Migrate dashboard_files → user_attachments; drop legacy table; normalize file refs.

Revision ID: schema_084
Revises: schema_083
"""

from __future__ import annotations

from alembic import op

revision = "schema_084"
down_revision = "schema_083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_attachments
          ADD COLUMN IF NOT EXISTS dashboard_id UUID NULL
            REFERENCES user_dashboards(id) ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_attachments_dashboard
          ON user_attachments (dashboard_id);
        """
    )
    op.execute(
        """
        INSERT INTO user_attachments (
          id, tenant_id, owner_user_id, dashboard_id, storage_relpath,
          content_type, size_bytes, original_name, created_at
        )
        SELECT
          id, tenant_id, owner_user_id, dashboard_id, storage_relpath,
          content_type, size_bytes, original_name, created_at
        FROM dashboard_files
        ON CONFLICT (id) DO NOTHING;
        """
    )
    op.execute(
        """
        UPDATE collection_items
        SET data = replace(data::text, 'wsfile:', 'file:')::jsonb
        WHERE data::text LIKE '%wsfile:%';
        """
    )
    op.execute(
        """
        UPDATE user_dashboards
        SET data = replace(data::text, 'wsfile:', 'file:')::jsonb
        WHERE data::text LIKE '%wsfile:%';
        """
    )
    op.execute("DROP TABLE IF EXISTS dashboard_files CASCADE;")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_files (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          dashboard_id UUID NOT NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
          storage_relpath TEXT NOT NULL UNIQUE,
          content_type TEXT NOT NULL,
          size_bytes BIGINT NOT NULL,
          original_name TEXT NOT NULL DEFAULT '',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        INSERT INTO dashboard_files (
          id, tenant_id, owner_user_id, dashboard_id, storage_relpath,
          content_type, size_bytes, original_name, created_at
        )
        SELECT
          id, tenant_id, owner_user_id, dashboard_id, storage_relpath,
          content_type, size_bytes, original_name, created_at
        FROM user_attachments
        WHERE dashboard_id IS NOT NULL
        ON CONFLICT (id) DO NOTHING;
        """
    )
    op.execute("ALTER TABLE user_attachments DROP COLUMN IF EXISTS dashboard_id;")
