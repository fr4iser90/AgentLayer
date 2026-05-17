"""scheduler_job_runs: persisted execution history for coding_agent schedules."""

from __future__ import annotations

from alembic import op

revision = "schema_054"
down_revision = "schema_053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_job_runs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          scheduler_job_id UUID NOT NULL REFERENCES scheduler_jobs(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          execution_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          workspace_id UUID NULL,
          agent_id TEXT NULL,
          status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed'))
            DEFAULT 'running',
          error TEXT NULL,
          summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_job_started
          ON scheduler_job_runs (scheduler_job_id, started_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduler_job_runs_tenant_started
          ON scheduler_job_runs (tenant_id, started_at DESC);
        """
    )
    op.execute(
        """
        COMMENT ON TABLE scheduler_job_runs IS
          'Execution history for scheduler_jobs (especially coding_agent): tools, git diff summary, outcome.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_job_runs;")
