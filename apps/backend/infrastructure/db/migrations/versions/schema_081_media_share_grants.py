"""media_share_grants — share owned uploads within tenant (license required).

Revision ID: schema_081
Revises: schema_080
"""

from __future__ import annotations

from alembic import op

revision = "schema_081"
down_revision = "schema_080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS media_share_grants (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          media_item_id UUID NOT NULL REFERENCES media_items(id) ON DELETE CASCADE,
          owner_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          viewer_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          permission TEXT NOT NULL DEFAULT 'play'
            CHECK (permission IN ('play', 'play_and_download')),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ,
          UNIQUE (media_item_id, viewer_user_id)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_share_grants_viewer
          ON media_share_grants (viewer_user_id, tenant_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_media_share_grants_owner
          ON media_share_grants (owner_user_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_media_share_grants_owner;")
    op.execute("DROP INDEX IF EXISTS idx_media_share_grants_viewer;")
    op.execute("DROP TABLE IF EXISTS media_share_grants;")
