"""Drop legacy users.ide_agent_allowed (IDE Agent removed)."""

from __future__ import annotations

from alembic import op

revision = "schema_052"
down_revision = "schema_051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ide_agent_allowed;")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS ide_agent_allowed BOOLEAN NOT NULL DEFAULT false;
        """
    )
