"""Operator legal page settings (Impressum, privacy, terms)."""

from __future__ import annotations

from alembic import op

revision = "schema_115"
down_revision = "schema_114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS legal_enabled BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS legal_jurisdiction VARCHAR(16) NOT NULL DEFAULT 'none',
          ADD COLUMN IF NOT EXISTS legal_entity_name VARCHAR(256) NULL,
          ADD COLUMN IF NOT EXISTS legal_entity_address TEXT NULL,
          ADD COLUMN IF NOT EXISTS legal_entity_email VARCHAR(256) NULL,
          ADD COLUMN IF NOT EXISTS legal_entity_phone VARCHAR(64) NULL,
          ADD COLUMN IF NOT EXISTS legal_terms_enabled BOOLEAN NOT NULL DEFAULT false,
          ADD COLUMN IF NOT EXISTS legal_impressum_md TEXT NULL,
          ADD COLUMN IF NOT EXISTS legal_privacy_md TEXT NULL,
          ADD COLUMN IF NOT EXISTS legal_terms_md TEXT NULL;
        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_legal_jurisdiction_check;
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_legal_jurisdiction_check
            CHECK (legal_jurisdiction IN ('none', 'de', 'en', 'custom'));
        COMMENT ON COLUMN operator_settings.legal_enabled IS
          'Show public legal pages and footer links (e.g. DE Impressum + Datenschutz).';
        COMMENT ON COLUMN operator_settings.legal_jurisdiction IS
          'Content pack under content/legal/{jurisdiction}/; none disables pages even if enabled.';
        COMMENT ON COLUMN operator_settings.legal_terms_enabled IS
          'Also expose terms/AGB page (recommended when accounts are offered).';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings DROP CONSTRAINT IF EXISTS operator_settings_legal_jurisdiction_check;
        ALTER TABLE operator_settings
          DROP COLUMN IF EXISTS legal_terms_md,
          DROP COLUMN IF EXISTS legal_privacy_md,
          DROP COLUMN IF EXISTS legal_impressum_md,
          DROP COLUMN IF EXISTS legal_terms_enabled,
          DROP COLUMN IF EXISTS legal_entity_phone,
          DROP COLUMN IF EXISTS legal_entity_email,
          DROP COLUMN IF EXISTS legal_entity_address,
          DROP COLUMN IF EXISTS legal_entity_name,
          DROP COLUMN IF EXISTS legal_jurisdiction,
          DROP COLUMN IF EXISTS legal_enabled;
        """
    )
