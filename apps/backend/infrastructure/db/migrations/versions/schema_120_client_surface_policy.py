"""Client surface policy on operator_settings (ADR 0009).

web_ui_enabled / api_key_clients_enabled / api_key_workspace_modes — presets
WEB_ONLY | WEB_AND_TUI | TUI_ONLY are derived from the two booleans.
"""

from __future__ import annotations

from alembic import op

revision = "schema_120"
down_revision = "schema_119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS web_ui_enabled BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS api_key_clients_enabled BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS api_key_workspace_modes VARCHAR(16) NOT NULL DEFAULT 'both';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_api_key_workspace_modes_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_api_key_workspace_modes_check
            CHECK (api_key_workspace_modes IN ('server', 'client', 'both'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.web_ui_enabled IS
          'When false, browser chat/dashboard SPA routes are refused (login/setup/admin stay). '
          'API and WebSocket remain. Pair with api_key_clients_enabled for WEB_ONLY / TUI_ONLY.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.api_key_clients_enabled IS
          'When false, user API keys cannot be minted or used (TUI/CLI/scripts). JWT sessions stay.';
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.api_key_workspace_modes IS
          'server | client | both: which project_workspaces.execution_mode API-key clients may create/bind. '
          'JWT/WebUI is not limited by this. Indexing still gated by workspace_index_consent_max.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_api_key_workspace_modes_check;
        """
    )
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS api_key_workspace_modes;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS api_key_clients_enabled;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS web_ui_enabled;")
