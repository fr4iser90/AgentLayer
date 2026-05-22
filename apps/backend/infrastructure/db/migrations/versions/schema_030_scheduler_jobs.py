"""Persisted scheduler jobs (chat/API); execution by target worker is separate.

Revision ID: schema_030
Revises: schema_029
"""

from __future__ import annotations

from alembic import op

revision = "schema_030"
down_revision = "schema_029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduler_jobs (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          execution_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          dashboard_id UUID NULL REFERENCES user_dashboards(id) ON DELETE SET NULL,
          execution_target TEXT NOT NULL
            CHECK (execution_target IN ('general', 'ide_agent')),
          title TEXT,
          instructions TEXT NOT NULL,
          interval_minutes INTEGER NOT NULL
            CHECK (interval_minutes >= 5 AND interval_minutes <= 10080),
          enabled BOOLEAN NOT NULL DEFAULT true,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_tenant_created
          ON scheduler_jobs (tenant_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_tenant_target
          ON scheduler_jobs (tenant_id, execution_target, enabled);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduler_jobs_dashboard
          ON scheduler_jobs (dashboard_id)
          WHERE dashboard_id IS NOT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON TABLE scheduler_jobs IS
          'Scheduled agent tasks; tools schedule_job_* write here. Workers pick rows by execution_target.';
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scheduler_jobs;")
