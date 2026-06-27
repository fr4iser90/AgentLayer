"""Keep smart-router model unset by default.

Revision ID: schema_104
Revises: schema_103
Create Date: 2026-06-26
"""

from alembic import op

revision = "schema_104"
down_revision = "schema_103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE operator_settings
        SET llm_router_model = ''
        WHERE llm_router_model IS NULL
           OR llm_router_model = 'nemotron-3-nano:4b';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_router_model SET DEFAULT '',
          ALTER COLUMN llm_router_model SET NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_router_model SET DEFAULT 'nemotron-3-nano:4b';
        """
    )
