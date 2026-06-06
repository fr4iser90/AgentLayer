"""Allow multiple personal and shared chat threads per dashboard.

Revision ID: schema_078
Revises: schema_077
"""

from __future__ import annotations

from alembic import op

revision = "schema_078"
down_revision = "schema_077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_chat_conv_user_dashboard_personal;")
    op.execute("DROP INDEX IF EXISTS uq_chat_conv_dashboard_shared;")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_conv_user_dashboard_personal_updated
        ON chat_conversations (user_id, dashboard_id, updated_at DESC)
        WHERE dashboard_id IS NOT NULL AND shared = false;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chat_conv_dashboard_shared_updated
        ON chat_conversations (dashboard_id, updated_at DESC)
        WHERE dashboard_id IS NOT NULL AND shared = true;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chat_conv_dashboard_shared_updated;")
    op.execute("DROP INDEX IF EXISTS idx_chat_conv_user_dashboard_personal_updated;")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conv_user_dashboard_personal
        ON chat_conversations (user_id, dashboard_id)
        WHERE dashboard_id IS NOT NULL AND shared = false;
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conv_dashboard_shared
        ON chat_conversations (dashboard_id)
        WHERE dashboard_id IS NOT NULL AND shared = true;
        """
    )
