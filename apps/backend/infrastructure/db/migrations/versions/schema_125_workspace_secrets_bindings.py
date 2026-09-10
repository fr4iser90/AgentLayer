"""schema_125: workspace-scoped secrets + DB env bindings (no file map).

Revision ID: schema_125
Revises: schema_124
"""

from __future__ import annotations

from alembic import op

revision = "schema_125"
down_revision = "schema_124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_workspace_secrets (
          id BIGSERIAL PRIMARY KEY,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          workspace_id UUID NOT NULL REFERENCES project_workspaces(id) ON DELETE CASCADE,
          service_key TEXT NOT NULL,
          ciphertext BYTEA NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (user_id, workspace_id, service_key)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_workspace_secrets_ws
          ON user_workspace_secrets (workspace_id);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_workspace_secrets_user
          ON user_workspace_secrets (user_id);
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_env_bindings (
          id BIGSERIAL PRIMARY KEY,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          workspace_id UUID NOT NULL REFERENCES project_workspaces(id) ON DELETE CASCADE,
          env_name TEXT NOT NULL,
          service_key TEXT NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (user_id, workspace_id, env_name),
          CHECK (env_name ~ '^[A-Za-z_][A-Za-z0-9_]*$'),
          CHECK (service_key ~ '^[a-z0-9][a-z0-9_.-]{0,62}$')
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_workspace_env_bindings_ws
          ON workspace_env_bindings (workspace_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workspace_env_bindings;")
    op.execute("DROP TABLE IF EXISTS user_workspace_secrets;")
