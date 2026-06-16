"""Per-model harness knob overrides (catalog_owned_by + model)."""

from __future__ import annotations

from alembic import op

revision = "schema_098"
down_revision = "schema_097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config_model_overrides (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          catalog_owned_by VARCHAR(128) NOT NULL,
          model VARCHAR(512) NOT NULL DEFAULT '',
          label VARCHAR(128) NULL,
          knobs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_by UUID NULL REFERENCES users(id) ON DELETE SET NULL
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_config_model_overrides_key
          ON agent_config_model_overrides (tenant_id, catalog_owned_by, model);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_config_model_overrides_tenant
          ON agent_config_model_overrides (tenant_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_config_model_overrides;")
