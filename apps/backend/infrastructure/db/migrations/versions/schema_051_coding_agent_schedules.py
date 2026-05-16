"""Replace ide_agent execution_target with coding_agent; rename workflow column."""

from __future__ import annotations

from alembic import op

revision = "schema_051"
down_revision = "schema_050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE scheduler_jobs
        SET execution_target = 'coding_agent'
        WHERE execution_target = 'ide_agent';

        UPDATE project_runs
        SET execution_target = 'coding_agent'
        WHERE execution_target = 'ide_agent';

        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_execution_target_check
          CHECK (execution_target IN ('server_periodic', 'coding_agent'));

        ALTER TABLE project_runs DROP CONSTRAINT IF EXISTS project_runs_execution_target_check;
        ALTER TABLE project_runs
          ADD CONSTRAINT project_runs_execution_target_check
          CHECK (execution_target IN ('coding_agent'));

        ALTER TABLE scheduler_jobs
          RENAME COLUMN ide_workflow TO coding_workflow;

        ALTER TABLE project_runs
          RENAME COLUMN ide_workflow TO coding_workflow;

        COMMENT ON COLUMN scheduler_jobs.coding_workflow IS
          'JSON: workspace_id (required for coding_agent), agent_id (coding|coding_plan), prompt_preamble';

        COMMENT ON COLUMN project_runs.coding_workflow IS
          'JSON: workspace_id, agent_id, prompt_preamble for coding agent run';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_jobs
          RENAME COLUMN coding_workflow TO ide_workflow;

        ALTER TABLE project_runs
          RENAME COLUMN coding_workflow TO ide_workflow;

        UPDATE scheduler_jobs
        SET execution_target = 'ide_agent'
        WHERE execution_target = 'coding_agent';

        UPDATE project_runs
        SET execution_target = 'ide_agent'
        WHERE execution_target = 'coding_agent';

        ALTER TABLE scheduler_jobs DROP CONSTRAINT IF EXISTS scheduler_jobs_execution_target_check;
        ALTER TABLE scheduler_jobs
          ADD CONSTRAINT scheduler_jobs_execution_target_check
          CHECK (execution_target IN ('server_periodic', 'ide_agent'));

        ALTER TABLE project_runs DROP CONSTRAINT IF EXISTS project_runs_execution_target_check;
        ALTER TABLE project_runs
          ADD CONSTRAINT project_runs_execution_target_check
          CHECK (execution_target IN ('ide_agent'));
        """
    )
