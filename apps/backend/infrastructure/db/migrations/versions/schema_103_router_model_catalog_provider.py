"""Smart router provider catalog id.

Revision ID: schema_103
Revises: schema_102
Create Date: 2026-06-26
"""

from alembic import op

revision = "schema_103"
down_revision = "schema_102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llm_router_model_catalog_owned_by VARCHAR(64);
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.llm_router_model_catalog_owned_by IS
          'Catalog provider id for the smart router model (provider_1, provider_33, ...).';
        """
    )
    op.execute(
        """
        UPDATE operator_settings
        SET llm_router_model = ''
        WHERE llm_router_model = 'nemotron-3-nano:4b';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_router_model SET DEFAULT '';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_router_model SET DEFAULT 'nemotron-3-nano:4b';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS llm_router_model_catalog_owned_by;
        """
    )
