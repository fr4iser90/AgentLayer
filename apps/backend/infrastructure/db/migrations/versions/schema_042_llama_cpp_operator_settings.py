"""Llama.cpp OpenAI-compatible server settings on operator_settings.

Revision ID: schema_042
Revises: schema_041
"""

from __future__ import annotations

from alembic import op

revision = "schema_042"
down_revision = "schema_041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_enabled BOOLEAN NOT NULL DEFAULT false;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_api_base VARCHAR(2048);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_api_header_name VARCHAR(128);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_api_key VARCHAR(512);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_router_model VARCHAR(256);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_model_default VARCHAR(256);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_model_vlm VARCHAR(256);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_model_agent VARCHAR(256);
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS llama_cpp_model_coding VARCHAR(256);
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_model_coding;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_model_agent;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_model_vlm;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_model_default;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_router_model;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_api_key;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_api_header_name;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_api_base;")
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS llama_cpp_enabled;")
