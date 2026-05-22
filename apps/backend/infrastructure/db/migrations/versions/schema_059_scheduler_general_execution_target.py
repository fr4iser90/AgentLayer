"""scheduler_jobs: normalize execution_target to general | coding_agent only."""

from __future__ import annotations

from alembic import op

revision = "schema_059"
down_revision = "schema_058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE scheduler_jobs
        SET execution_target = 'general'
        WHERE execution_target IS DISTINCT FROM 'general'
          AND execution_target IS DISTINCT FROM 'coding_agent';

        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_execution_target_check
          CHECK (execution_target IN ('general', 'coding_agent'));

        COMMENT ON COLUMN scheduler_jobs.execution_target IS
          'general = General chat agent (plugins/agents/general); coding_agent = coding agent on workspace';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_execution_target_check
          CHECK (execution_target IN ('general', 'coding_agent'));
        """
    )
