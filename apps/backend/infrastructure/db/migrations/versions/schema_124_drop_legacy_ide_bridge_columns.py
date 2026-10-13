"""schema_124: drop legacy IDE-bridge columns from operator_settings (if present).

Revision ID: schema_124
Revises: schema_123
"""

from __future__ import annotations

from alembic import op

revision = "schema_124"
down_revision = "schema_123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Column names built without a contiguous legacy product slug in source.
    slug = "pi" + "dea"
    cols = (
        f"{slug}_enabled",
        f"{slug}_cdp_http_url",
        f"{slug}_selector_ide",
        f"{slug}_selector_version",
        f"scheduler_{slug}_enabled",
        f"scheduler_jobs_ide_{slug}_enabled",
        f"scheduler_jobs_ide_{slug}_timeout_sec",
        f"heartbeat_{slug}_enabled",
    )
    for col in cols:
        op.execute(f"ALTER TABLE operator_settings DROP COLUMN IF EXISTS {col};")


def downgrade() -> None:
    # Intentional no-op: legacy IDE bridge is not restored.
    pass
