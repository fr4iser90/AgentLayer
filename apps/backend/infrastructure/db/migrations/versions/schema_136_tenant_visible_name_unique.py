"""Tenant-visible workspaces are unique by name within their tenant.

``project_workspaces`` has always been ``UNIQUE (owner_user_id, name)``. That is
the right rule for private workspaces and the wrong rule for company ones: it
lets two members of the same tenant each create ``repo``, and the tenant disk
root ``<base>/_tenants/<tenant_id>/<name>`` gives them the same directory. The
old constraint permits what the new placement cannot hold.

So the tenant namespace gets its own rule, as a partial unique index:

    UNIQUE (tenant_id, name) WHERE visibility = 'tenant'

Partial rather than a table-wide constraint for two reasons. Private workspaces
keep their existing per-owner rule untouched — two people may each have a
private ``repo`` and that must stay legal. And the index covers only the rows
that need it, so it costs nothing on the private majority.

Why this is safe to add now
-------------------------
``visibility`` arrived in ``schema_135`` defaulting every existing row to
``private``, and nothing writes ``tenant`` until the create flow grows the
switch. The index is therefore empty on creation and cannot fail against
existing data. If it ever were applied to a database that already had
duplicate tenant-visible names, it would fail loudly rather than pick a
winner — the correct outcome for a constraint that is about to become load
bearing.

The index is what makes the create path safe to materialise before inserting.
Without it, two concurrent creates of the same company name would both reach
the same directory and the loser would be left holding a path somebody else
owns.
"""

from __future__ import annotations

from alembic import op

revision = "schema_136"
down_revision = "schema_135"
branch_labels = None
depends_on = None

_INDEX = "project_workspaces_tenant_visible_name_key"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS {_INDEX}
          ON project_workspaces (tenant_id, name)
          WHERE visibility = 'tenant';
        """
    )
    op.execute(
        f"""
        COMMENT ON INDEX {_INDEX} IS
          'Company-wide name uniqueness for tenant-visible workspaces. Private '
          'workspaces are outside this index and keep UNIQUE (owner_user_id, '
          'name), so two members may each hold a private workspace of the same '
          'name. Backs the shared disk root <workspace_base>/_tenants/'
          '<tenant_id>/<name>: one tenant, one name, one directory.';
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {_INDEX};")
