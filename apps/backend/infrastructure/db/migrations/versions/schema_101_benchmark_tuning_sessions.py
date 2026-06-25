"""Benchmark autotune sessions."""

from __future__ import annotations

from alembic import op

revision = "schema_101"
down_revision = "schema_100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS benchmark_tuning_sessions (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id INTEGER NOT NULL,
          user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          status VARCHAR(32) NOT NULL DEFAULT 'queued',
          mode VARCHAR(32) NOT NULL DEFAULT 'fast',
          catalog_owned_by VARCHAR(64) NOT NULL,
          model TEXT NOT NULL,
          profiles_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          attempts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
          best_run_id UUID NULL REFERENCES benchmark_runs(id) ON DELETE SET NULL,
          best_score DOUBLE PRECISION NULL,
          best_patches_json JSONB NULL,
          promoted_at TIMESTAMPTZ NULL,
          error_text TEXT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_benchmark_tuning_sessions_tenant_created
          ON benchmark_tuning_sessions (tenant_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_benchmark_tuning_sessions_status
          ON benchmark_tuning_sessions (tenant_id, status, created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS benchmark_tuning_sessions;")
