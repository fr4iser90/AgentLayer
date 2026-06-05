"""Index refresh_tokens.token_hash for O(1) session lookup."""

from __future__ import annotations

from alembic import op

revision = "schema_073"
down_revision = "schema_072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash
          ON refresh_tokens (token_hash);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_refresh_tokens_token_hash;")
