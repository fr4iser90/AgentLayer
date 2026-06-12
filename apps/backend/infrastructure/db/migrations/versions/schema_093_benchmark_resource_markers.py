"""DB markers for benchmark sandboxes (workspaces, dashboards, conversations)."""

from __future__ import annotations

from alembic import op

revision = "schema_093"
down_revision = "schema_092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS benchmark_workspace_quota INTEGER NOT NULL DEFAULT 10;

        COMMENT ON COLUMN users.benchmark_workspace_quota IS
          'Max benchmark-tagged workspaces (benchmark_run_id set); does not use workspace_quota.';

        ALTER TABLE project_workspaces
          ADD COLUMN IF NOT EXISTS benchmark_run_id UUID NULL
            REFERENCES benchmark_runs(id) ON DELETE CASCADE;

        ALTER TABLE user_dashboards
          ADD COLUMN IF NOT EXISTS benchmark_run_id UUID NULL
            REFERENCES benchmark_runs(id) ON DELETE CASCADE;

        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS benchmark_run_id UUID NULL
            REFERENCES benchmark_runs(id) ON DELETE CASCADE;

        CREATE INDEX IF NOT EXISTS idx_project_workspaces_benchmark_run
          ON project_workspaces (owner_user_id, benchmark_run_id)
          WHERE benchmark_run_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_user_dashboards_benchmark_run
          ON user_dashboards (owner_user_id, benchmark_run_id)
          WHERE benchmark_run_id IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_chat_conversations_benchmark_run
          ON chat_conversations (user_id, benchmark_run_id)
          WHERE benchmark_run_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP INDEX IF EXISTS idx_chat_conversations_benchmark_run;
        DROP INDEX IF EXISTS idx_user_dashboards_benchmark_run;
        DROP INDEX IF EXISTS idx_project_workspaces_benchmark_run;

        ALTER TABLE chat_conversations DROP COLUMN IF EXISTS benchmark_run_id;
        ALTER TABLE user_dashboards DROP COLUMN IF EXISTS benchmark_run_id;
        ALTER TABLE project_workspaces DROP COLUMN IF EXISTS benchmark_run_id;
        ALTER TABLE users DROP COLUMN IF EXISTS benchmark_workspace_quota;
        """
    )
