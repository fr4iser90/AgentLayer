"""scheduler_jobs: execution_target stores agent_id; drop fixed CHECK; normalize old coding_agent rows."""

from __future__ import annotations

from alembic import op

revision = "schema_060"
down_revision = "schema_059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE scheduler_jobs
        SET execution_target = 'coding'
        WHERE execution_target = 'coding_agent';

        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;

        COMMENT ON COLUMN scheduler_jobs.execution_target IS
          'Registry agent_id (plugins/agents); validated at insert';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE scheduler_jobs
        SET execution_target = 'coding_agent'
        WHERE execution_target = 'coding';

        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_execution_target_check
          CHECK (execution_target IN ('general', 'coding_agent'));
        """
    )
