"""scheduler_jobs: coding_agent schedules use agent_id=coding (not coding_plan)."""

from __future__ import annotations

from alembic import op

revision = "schema_055"
down_revision = "schema_054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE scheduler_jobs
        SET coding_workflow = jsonb_set(
              COALESCE(coding_workflow, '{}'::jsonb),
              '{agent_id}',
              '"coding"'::jsonb,
              true
            ),
            updated_at = now()
        WHERE execution_target = 'coding_agent'
          AND COALESCE(coding_workflow->>'agent_id', '') IN ('coding_plan', '');
        """
    )


def downgrade() -> None:
    pass
