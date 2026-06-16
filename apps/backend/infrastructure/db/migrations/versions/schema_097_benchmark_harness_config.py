"""Per-tenant benchmark harness defaults and per-model overrides."""

from __future__ import annotations

from alembic import op

revision = "schema_097"
down_revision = "schema_096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_harness_config (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          catalog_owned_by VARCHAR(128) NULL,
          model VARCHAR(512) NULL,
          label VARCHAR(128) NULL,
          harness_preset VARCHAR(64) NOT NULL DEFAULT 'observability',
          max_tool_rounds_override INTEGER NULL,
          scenario_timeout_sec DOUBLE PRECISION NULL,
          capture_timeline BOOLEAN NULL,
          stream_llm BOOLEAN NULL,
          notes TEXT NULL,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_by UUID NULL REFERENCES users(id) ON DELETE SET NULL
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_benchmark_harness_config_key
          ON benchmark_harness_config (
            tenant_id,
            COALESCE(catalog_owned_by, ''),
            COALESCE(model, '')
          );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_benchmark_harness_config_tenant
          ON benchmark_harness_config (tenant_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_harness_config;")
