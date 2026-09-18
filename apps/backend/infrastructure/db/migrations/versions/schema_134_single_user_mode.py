"""Add ``single_user`` as a third ``deployment_mode``.

``agent_system`` and ``multi_tenant`` differ by whether the organization
surface exists. Neither says "this instance is one person". ``single_user`` is
that: login stays required, but user administration, tenant selection and the
/org surface are not part of the product.

It is a UI reduction, not a security boundary — there is nothing to isolate
the single user from. The API stays reachable; what changes is that the
application stops offering the multi-user surfaces.

Every existing guard is written ``!= "multi_tenant"``, so a third value would
otherwise slip through them and behave like ``agent_system`` by accident.
``operator_settings.has_org_surface()`` replaces those comparisons with the
intent, so adding a mode forces a decision instead of inheriting one.
"""

from __future__ import annotations

from alembic import op

revision = "schema_134"
down_revision = "schema_133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_deployment_mode_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_deployment_mode_check
          CHECK (deployment_mode IN ('single_user', 'agent_system', 'multi_tenant'));
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN operator_settings.deployment_mode IS
          'single_user = one person, no user admin / tenant picker / /org UI '
          '(login still required); agent_system = single team (no /org UI); '
          'multi_tenant = organizations product.';
        """
    )


def downgrade() -> None:
    # Collapse single_user onto agent_system before narrowing, or the constraint
    # re-add fails on rows that no longer have a legal value.
    op.execute(
        """
        UPDATE operator_settings SET deployment_mode = 'agent_system'
          WHERE deployment_mode = 'single_user';
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          DROP CONSTRAINT IF EXISTS operator_settings_deployment_mode_check;
        """
    )
    op.execute(
        """
        ALTER TABLE operator_settings
          ADD CONSTRAINT operator_settings_deployment_mode_check
          CHECK (deployment_mode IN ('agent_system', 'multi_tenant'));
        """
    )
