"""user_connector_profiles — reusable HTTP API connector definitions per user.

Revision ID: schema_082
Revises: schema_081
"""

from __future__ import annotations

from alembic import op

revision = "schema_082"
down_revision = "schema_081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_connector_profiles (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          profile_id TEXT NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          base_url TEXT NOT NULL,
          auth JSONB NOT NULL DEFAULT '{}'::jsonb,
          default_headers JSONB NOT NULL DEFAULT '{}'::jsonb,
          endpoints JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (user_id, profile_id),
          CHECK (profile_id ~ '^[a-z][a-z0-9_-]{0,63}$')
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_connector_profiles_user
          ON user_connector_profiles (user_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_connector_profiles;")
