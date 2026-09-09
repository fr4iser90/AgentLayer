"""Rename heartbeat_* → scheduler_* (operator_settings + outbound table).

Revision ID: schema_029
Revises: schema_028
"""

from __future__ import annotations

from alembic import op

revision = "schema_029"
down_revision = "schema_028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_enabled TO scheduler_enabled;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_interval_minutes TO scheduler_interval_minutes;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_user_id TO scheduler_user_id;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_model TO scheduler_model;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_max_tool_rounds TO scheduler_max_tool_rounds;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_notify_only_if_not_ok TO scheduler_notify_only_if_not_ok;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_max_outbound_per_day TO scheduler_max_outbound_per_day;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_allowed_tool_packages TO scheduler_allowed_tool_packages;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_llm_backend TO scheduler_llm_backend;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_tools_mode TO scheduler_tools_mode;
        ALTER TABLE operator_settings RENAME COLUMN heartbeat_instructions TO scheduler_instructions;
        """
    )
    op.execute(
        """
        ALTER TABLE heartbeat_outbound_daily RENAME TO scheduler_outbound_daily;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.scheduler_user_id IS
          'User identity for scheduler tools/tenant; required when scheduler_enabled.';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE scheduler_outbound_daily RENAME TO heartbeat_outbound_daily;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings RENAME COLUMN scheduler_enabled TO heartbeat_enabled;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_interval_minutes TO heartbeat_interval_minutes;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_user_id TO heartbeat_user_id;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_model TO heartbeat_model;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_max_tool_rounds TO heartbeat_max_tool_rounds;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_notify_only_if_not_ok TO heartbeat_notify_only_if_not_ok;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_max_outbound_per_day TO heartbeat_max_outbound_per_day;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_allowed_tool_packages TO heartbeat_allowed_tool_packages;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_llm_backend TO heartbeat_llm_backend;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_tools_mode TO heartbeat_tools_mode;
        ALTER TABLE operator_settings RENAME COLUMN scheduler_instructions TO heartbeat_instructions;
        """
    )
