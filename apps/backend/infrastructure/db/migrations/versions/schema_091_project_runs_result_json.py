"""project_runs: persist execution summary (tools, git, agent_run_id) for benchmarks."""

from __future__ import annotations

from alembic import op

revision = "schema_091"
down_revision = "schema_090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_runs
          ADD COLUMN IF NOT EXISTS result_json JSONB NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE project_runs
          DROP COLUMN IF EXISTS result_json;
        """
    )
