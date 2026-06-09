"""Persisted agent LLM benchmark runs (admin UI + history)."""

from __future__ import annotations

from alembic import op

revision = "schema_090"
down_revision = "schema_089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_runs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'queued',
          suite VARCHAR(64) NOT NULL,
          manifest_path TEXT NOT NULL,
          profiles_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          report_json JSONB NULL,
          summary_json JSONB NULL,
          error_text TEXT NULL,
          resource_prefix TEXT NULL,
          started_at TIMESTAMPTZ NULL,
          finished_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_benchmark_runs_tenant_created
          ON benchmark_runs (tenant_id, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_runs;")
