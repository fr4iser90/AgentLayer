"""Unify catalog provider ids (provider_33+ for admin) and scheduler backend naming.

Revision ID: schema_069
Revises: schema_068
"""

from __future__ import annotations

from alembic import op

revision = "schema_069"
down_revision = "schema_068"
branch_labels = None
depends_on = None

# Env slots: provider_1 … provider_32 (see llm_env_providers.LLM_ENV_PROVIDER_MAX)
_ADMIN_PROVIDER_OFFSET = 32


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE operator_settings
        SET scheduler_llm_backend = 'provider'
        WHERE lower(trim(scheduler_llm_backend)) IN ('catalog', 'ollama');

        UPDATE operator_settings
        SET scheduler_llm_backend = 'provider_admin'
        WHERE lower(trim(scheduler_llm_backend)) = 'external';

        UPDATE operator_settings
        SET llm_primary_backend = 'provider'
        WHERE lower(trim(llm_primary_backend)) IN ('catalog', 'ollama');

        UPDATE operator_settings
        SET llm_primary_backend = 'provider_admin'
        WHERE lower(trim(llm_primary_backend)) = 'external';

        ALTER TABLE operator_settings
          ALTER COLUMN llm_primary_backend SET DEFAULT 'provider';

        UPDATE chat_conversations
        SET pref_model_catalog_owned_by = 'provider_' || ({_ADMIN_PROVIDER_OFFSET} + CAST(
              substring(pref_model_catalog_owned_by FROM '^external_([0-9]+)$') AS INTEGER
            ))::text
        WHERE pref_model_catalog_owned_by ~ '^external_[0-9]+$';

        UPDATE chat_conversations
        SET pref_model_catalog_owned_by = 'provider_failover'
        WHERE lower(trim(pref_model_catalog_owned_by)) = 'external';
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE operator_settings
        SET scheduler_llm_backend = 'catalog'
        WHERE lower(trim(scheduler_llm_backend)) = 'provider';

        UPDATE operator_settings
        SET scheduler_llm_backend = 'external'
        WHERE lower(trim(scheduler_llm_backend)) = 'provider_admin';

        UPDATE operator_settings
        SET llm_primary_backend = 'catalog'
        WHERE lower(trim(llm_primary_backend)) = 'provider';

        UPDATE operator_settings
        SET llm_primary_backend = 'external'
        WHERE lower(trim(llm_primary_backend)) = 'provider_admin';

        ALTER TABLE operator_settings
          ALTER COLUMN llm_primary_backend SET DEFAULT 'catalog';

        UPDATE chat_conversations
        SET pref_model_catalog_owned_by = 'external_' || (
              CAST(substring(pref_model_catalog_owned_by FROM '^provider_([0-9]+)$') AS INTEGER)
              - {_ADMIN_PROVIDER_OFFSET}
            )::text
        WHERE pref_model_catalog_owned_by ~ '^provider_[0-9]+$'
          AND CAST(substring(pref_model_catalog_owned_by FROM '^provider_([0-9]+)$') AS INTEGER)
              > {_ADMIN_PROVIDER_OFFSET};

        UPDATE chat_conversations
        SET pref_model_catalog_owned_by = 'external'
        WHERE lower(trim(pref_model_catalog_owned_by)) = 'provider_failover';
        """
    )
