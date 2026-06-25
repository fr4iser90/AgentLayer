"""Operator model catalog visibility preferences."""

from __future__ import annotations

from alembic import op

revision = "schema_100"
down_revision = "schema_099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_model_catalog_prefs (
          provider_id VARCHAR(64) NOT NULL,
          model_id TEXT NOT NULL,
          visible_in_chat BOOLEAN NOT NULL DEFAULT true,
          profile_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
          sort_order INTEGER NOT NULL DEFAULT 0,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (provider_id, model_id),
          CONSTRAINT operator_model_catalog_prefs_provider_id_check
            CHECK (provider_id ~ '^[a-z0-9_-]{1,64}$')
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_operator_model_catalog_prefs_visible
          ON operator_model_catalog_prefs (provider_id, visible_in_chat, sort_order, model_id);
        """
    )
    op.execute(
        """
        COMMENT ON TABLE operator_model_catalog_prefs IS
          'Admin preferences for model catalog rows. Missing rows are visible by default.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operator_model_catalog_prefs;")
