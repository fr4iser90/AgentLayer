"""Public read-only dashboard share links (optional block scope)."""

from __future__ import annotations

from alembic import op

revision = "schema_071"
down_revision = "schema_070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dashboard_public_share_tokens (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          dashboard_id UUID NOT NULL REFERENCES user_dashboards(id) ON DELETE CASCADE,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          token_hash TEXT NOT NULL,
          label TEXT NOT NULL DEFAULT '',
          block_ids TEXT[] NOT NULL DEFAULT '{}',
          expires_at TIMESTAMPTZ NULL,
          created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          revoked_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_dashboard_public_share_token_hash
        ON dashboard_public_share_tokens (token_hash);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_dashboard_public_share_dashboard
        ON dashboard_public_share_tokens (dashboard_id, tenant_id)
        WHERE revoked_at IS NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dashboard_public_share_tokens;")
