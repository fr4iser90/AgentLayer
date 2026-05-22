"""Agent tasks, artifacts, persisted agent runs, tool_invocation correlation.

Revision ID: schema_057
Revises: schema_056
"""

from __future__ import annotations

from alembic import op

revision = "schema_057"
down_revision = "schema_056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tasks (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          scope TEXT NOT NULL CHECK (scope IN ('global', 'workspace')),
          workspace_id UUID NULL REFERENCES project_workspaces(id) ON DELETE SET NULL,
          parent_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
          root_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
          blocked_by_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
          conversation_id UUID NULL REFERENCES chat_conversations(id) ON DELETE SET NULL,
          task_type TEXT NOT NULL DEFAULT 'general',
          goal TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
            'draft', 'planning', 'queued', 'in_progress', 'blocked', 'done', 'cancelled'
          )),
          priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high')),
          assigned_agent_id TEXT NULL,
          source TEXT NOT NULL DEFAULT 'user',
          requirements JSONB NOT NULL DEFAULT '[]'::jsonb,
          artifact_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
          metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CHECK (
            (scope = 'global' AND workspace_id IS NULL)
            OR (scope = 'workspace' AND workspace_id IS NOT NULL)
          )
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_tenant_status
          ON agent_tasks (tenant_id, status, updated_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_workspace
          ON agent_tasks (workspace_id, status, updated_at DESC)
          WHERE workspace_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_parent
          ON agent_tasks (parent_task_id)
          WHERE parent_task_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_tasks_root
          ON agent_tasks (root_task_id, updated_at DESC)
          WHERE root_task_id IS NOT NULL;
        """
    )
    op.execute(
        """
        COMMENT ON TABLE agent_tasks IS
          'Hierarchical work units: global (orchestrator) or workspace-scoped backlog.';
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_artifacts (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          created_by_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          workspace_id UUID NULL REFERENCES project_workspaces(id) ON DELETE SET NULL,
          kind TEXT NOT NULL DEFAULT 'report',
          summary TEXT NOT NULL DEFAULT '',
          content JSONB NOT NULL DEFAULT '{}'::jsonb,
          content_ref TEXT NULL,
          created_by_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
          created_by_run_id UUID NULL,
          metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_artifacts_task
          ON agent_artifacts (created_by_task_id, created_at DESC)
          WHERE created_by_task_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_artifacts_workspace
          ON agent_artifacts (workspace_id, created_at DESC)
          WHERE workspace_id IS NOT NULL;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
          id UUID PRIMARY KEY,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL,
          parent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL,
          conversation_id UUID NULL REFERENCES chat_conversations(id) ON DELETE SET NULL,
          workspace_id UUID NULL REFERENCES project_workspaces(id) ON DELETE SET NULL,
          agent_id TEXT NULL,
          status TEXT NOT NULL DEFAULT 'running' CHECK (status IN (
            'running', 'succeeded', 'failed', 'cancelled'
          )),
          token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
          error TEXT NULL,
          embedded_subagent BOOLEAN NOT NULL DEFAULT false,
          started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_runs_tenant_started
          ON agent_runs (tenant_id, started_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_runs_task
          ON agent_runs (task_id, started_at DESC)
          WHERE task_id IS NOT NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_agent_runs_parent
          ON agent_runs (parent_run_id)
          WHERE parent_run_id IS NOT NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE agent_artifacts
          ADD CONSTRAINT agent_artifacts_created_by_run_id_fkey
          FOREIGN KEY (created_by_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE tool_invocations
          ADD COLUMN IF NOT EXISTS agent_run_id UUID NULL REFERENCES agent_runs(id) ON DELETE SET NULL;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_tool_invocations_agent_run
          ON tool_invocations (agent_run_id, created_at DESC)
          WHERE agent_run_id IS NOT NULL;
        """
    )

    op.execute(
        """
        ALTER TABLE chat_conversations
          ADD COLUMN IF NOT EXISTS active_task_id UUID NULL REFERENCES agent_tasks(id) ON DELETE SET NULL;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_conversations DROP COLUMN IF EXISTS active_task_id;")
    op.execute("ALTER TABLE tool_invocations DROP COLUMN IF EXISTS agent_run_id;")
    op.execute("DROP TABLE IF EXISTS agent_artifacts CASCADE;")
    op.execute("DROP TABLE IF EXISTS agent_runs CASCADE;")
    op.execute("DROP TABLE IF EXISTS agent_tasks CASCADE;")
