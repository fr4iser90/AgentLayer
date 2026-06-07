"""Domain collections — source of truth for board content (dashboards are views).

Revision ID: schema_083
Revises: schema_082
"""

from __future__ import annotations

from alembic import op

revision = "schema_083"
down_revision = "schema_082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_collections (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          slug TEXT NOT NULL,
          title TEXT NOT NULL DEFAULT '',
          schema_hint TEXT NULL,
          metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (slug ~ '^[a-z][a-z0-9._-]{0,95}$'),
          UNIQUE (owner_user_id, slug)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_collections_owner
          ON user_collections (owner_user_id, tenant_id);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_items (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          collection_id UUID NOT NULL REFERENCES user_collections(id) ON DELETE CASCADE,
          list_key TEXT NOT NULL DEFAULT 'items',
          row_id TEXT NOT NULL,
          sort_order INT NOT NULL DEFAULT 0,
          data JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (collection_id, list_key, row_id)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_collection_items_list
          ON collection_items (collection_id, list_key, sort_order);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_attachments (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          collection_id UUID NULL REFERENCES user_collections(id) ON DELETE SET NULL,
          collection_item_id UUID NULL REFERENCES collection_items(id) ON DELETE SET NULL,
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
        CREATE INDEX IF NOT EXISTS idx_user_attachments_owner
          ON user_attachments (owner_user_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_attachments_collection
          ON user_attachments (collection_id);
        """
    )
    op.execute(
        """
        ALTER TABLE user_dashboards
          ADD COLUMN IF NOT EXISTS view_bindings JSONB NOT NULL DEFAULT '{}'::jsonb;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_dashboards DROP COLUMN IF EXISTS view_bindings;")
    op.execute("DROP TABLE IF EXISTS user_attachments;")
    op.execute("DROP TABLE IF EXISTS collection_items;")
    op.execute("DROP TABLE IF EXISTS user_collections;")
