"""Ephemeral vault for chat secret ingress (ADR 0006).

Revision ID: schema_043
Revises: schema_042
"""

from __future__ import annotations

from alembic import op

revision = "schema_043"
down_revision = "schema_042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_secret_vault (
          id UUID PRIMARY KEY,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          slot TEXT NOT NULL,
          ciphertext BYTEA NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          expires_at TIMESTAMPTZ NOT NULL,
          consumed_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_secret_vault_user_exp
          ON chat_secret_vault (user_id, expires_at);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_chat_secret_vault_tenant
          ON chat_secret_vault (tenant_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chat_secret_vault_tenant;")
    op.execute("DROP INDEX IF EXISTS ix_chat_secret_vault_user_exp;")
    op.execute("DROP TABLE IF EXISTS chat_secret_vault;")
