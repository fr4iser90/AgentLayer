"""schema_129: operator_settings.dashboards_allowed — global dashboard feature gate.

Per the roles/agent-assignment roadmap (P4): the operator-wide default for dashboards, after
the Vorbild of ``workspace_allow_self_editing``. Defaults true so dashboards stay enabled for
existing installs; the operator may disable dashboards for the whole instance. Per-user
``users.dashboards_allowed`` / ``dashboard_quota`` cover the remaining granularity.
"""

from __future__ import annotations

from alembic import op

revision = "schema_129"
down_revision = "schema_128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS dashboards_allowed BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.dashboards_allowed IS
          'Operator-wide dashboard feature gate (default true). When false, dashboards are disabled '
          'for the whole instance; per-user grants cannot re-enable them.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS dashboards_allowed;")
