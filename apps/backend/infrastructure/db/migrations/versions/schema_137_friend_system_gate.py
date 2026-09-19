"""schema_137: operator_settings.friend_system_enabled — global friendship/sharing gate.

Before this column the friendship subsystem had no switch of any kind: no operator setting, no
deployment-mode predicate, and both routers were registered with no dependency at all. The nav
allowlist could not express it either, because ``friends`` is absent from KNOWN_NAV_ITEMS, so a
tenant config asking for it to be dropped was silently discarded. That left hiding the settings
page as the only control, and the API reachable by every authenticated user in every mode.

This follows the ``dashboards_allowed`` pattern (schema_129). Defaults true so existing installs
keep working -- the gate is the point, not the starting state. When false, /v1/friends and
/v1/shares both 404 rather than 403: a subsystem that is not deployed should not announce that
it exists, matching how the /org surface 404s when the org surface is off.
"""

from __future__ import annotations

from alembic import op

revision = "schema_137"
down_revision = "schema_136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD COLUMN IF NOT EXISTS friend_system_enabled BOOLEAN NOT NULL DEFAULT true;
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.friend_system_enabled IS
          'Operator-wide friendship and peer-sharing gate (default true). When false, /v1/friends '
          'and /v1/shares return 404 for every caller; existing friendship rows are left untouched, '
          'so re-enabling restores them rather than requiring a migration.';
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE operator_settings DROP COLUMN IF EXISTS friend_system_enabled;")
