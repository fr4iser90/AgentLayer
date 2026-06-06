"""Media library: operator/user flags + media_items metadata table.

Revision ID: schema_080
Revises: schema_079
"""

from __future__ import annotations

from alembic import op

revision = "schema_080"
down_revision = "schema_079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_library_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_user_upload_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_sharing_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_default_user_quota_mb INTEGER;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_upload_max_file_mb INTEGER;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_upload_allowed_mime TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings ADD COLUMN IF NOT EXISTS
          media_embed_allowed_hosts TEXT;
        """
    )
    op.execute(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS media_enabled BOOLEAN;
        """
    )
    op.execute(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS media_storage_quota_mb INTEGER;
        """
    )
    op.execute(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS media_upload_enabled BOOLEAN;
        """
    )
    op.execute(
        """
        ALTER TABLE users ADD COLUMN IF NOT EXISTS media_sharing_enabled BOOLEAN;
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS media_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          dashboard_id UUID,

          source_kind TEXT NOT NULL CHECK (source_kind IN (
            'embed', 'upload', 'external_link', 'archive'
          )),

          storage_relpath TEXT UNIQUE,
          content_type TEXT,
          size_bytes BIGINT NOT NULL DEFAULT 0,
          original_name TEXT NOT NULL DEFAULT '',

          external_url TEXT,
          embed_provider TEXT,

          title TEXT NOT NULL DEFAULT '',
          artist TEXT NOT NULL DEFAULT '',
          album TEXT NOT NULL DEFAULT '',
          duration_sec INTEGER,
          cover_url TEXT,

          license TEXT CHECK (license IS NULL OR license IN (
            'owned', 'cc-by', 'cc-by-sa', 'cc0', 'other'
          )),
          license_note TEXT NOT NULL DEFAULT '',

          tags TEXT[] NOT NULL DEFAULT '{}',
          metadata JSONB NOT NULL DEFAULT '{}',

          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          deleted_at TIMESTAMPTZ,

          CONSTRAINT media_upload_has_storage CHECK (
            source_kind <> 'upload' OR (
              storage_relpath IS NOT NULL
              AND content_type IS NOT NULL
              AND size_bytes > 0
            )
          ),
          CONSTRAINT media_remote_has_url CHECK (
            source_kind NOT IN ('embed', 'external_link', 'archive')
            OR external_url IS NOT NULL
          )
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_items_owner
          ON media_items (owner_user_id, created_at DESC)
          WHERE deleted_at IS NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_items_dashboard
          ON media_items (dashboard_id)
          WHERE deleted_at IS NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_items_tenant_kind
          ON media_items (tenant_id, source_kind)
          WHERE deleted_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_media_items_tenant_kind;")
    op.execute("DROP INDEX IF EXISTS idx_media_items_dashboard;")
    op.execute("DROP INDEX IF EXISTS idx_media_items_owner;")
    op.execute("DROP TABLE IF EXISTS media_items;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS media_sharing_enabled;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS media_upload_enabled;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS media_storage_quota_mb;")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS media_enabled;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_embed_allowed_hosts;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_upload_allowed_mime;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_upload_max_file_mb;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_default_user_quota_mb;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_sharing_enabled;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_user_upload_enabled;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS media_library_enabled;")
