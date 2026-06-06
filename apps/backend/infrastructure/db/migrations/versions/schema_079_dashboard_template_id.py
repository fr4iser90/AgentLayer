"""Add ``template_id`` to user_dashboards (gallery snapshot reference; ``kind`` stays legacy).

Revision ID: schema_079
Revises: schema_078
"""

from __future__ import annotations

from alembic import op

revision = "schema_079"
down_revision = "schema_078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_dashboards
        ADD COLUMN IF NOT EXISTS template_id TEXT NULL;
        """
    )
    op.execute(
        """
        UPDATE user_dashboards
        SET template_id = kind || '-v1'
        WHERE template_id IS NULL
          AND kind IS NOT NULL
          AND btrim(kind) <> ''
          AND lower(btrim(kind)) <> 'custom';
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_user_dashboards_template_id
        ON user_dashboards (tenant_id, template_id)
        WHERE template_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_dashboards_template_id;")
    op.execute("ALTER TABLE user_dashboards DROP COLUMN IF EXISTS template_id;")
