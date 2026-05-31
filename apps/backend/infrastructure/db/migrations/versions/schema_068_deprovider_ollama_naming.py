"""Drop Ollama-specific operator naming; use catalog provider terminology.

Revision ID: schema_068
Revises: schema_067
"""

from __future__ import annotations

from alembic import op

revision = "schema_068"
down_revision = "schema_067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'operator_settings'
              AND column_name = 'llm_router_ollama_model'
          ) THEN
            ALTER TABLE operator_settings
              RENAME COLUMN llm_router_ollama_model TO llm_router_model;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        UPDATE operator_settings
        SET llm_primary_backend = 'catalog'
        WHERE llm_primary_backend IS NULL
           OR trim(llm_primary_backend) = ''
           OR lower(trim(llm_primary_backend)) = 'ollama';
        """
    )
    op.execute(
        """
        UPDATE operator_settings
        SET scheduler_llm_backend = 'catalog'
        WHERE lower(trim(scheduler_llm_backend)) = 'ollama';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_primary_backend SET DEFAULT 'catalog';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.llm_router_model IS
          'Smart-router model id on the catalog env provider (LLM_PROVIDER_*), not vendor-specific.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE operator_settings
        SET llm_primary_backend = 'ollama'
        WHERE lower(trim(llm_primary_backend)) = 'catalog';
        """
    )
    op.execute(
        """
        UPDATE operator_settings
        SET scheduler_llm_backend = 'ollama'
        WHERE lower(trim(scheduler_llm_backend)) = 'catalog';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ALTER COLUMN llm_primary_backend SET DEFAULT 'ollama';
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'operator_settings'
              AND column_name = 'llm_router_model'
          ) THEN
            ALTER TABLE operator_settings
              RENAME COLUMN llm_router_model TO llm_router_ollama_model;
          END IF;
        END $$;
        """
    )
