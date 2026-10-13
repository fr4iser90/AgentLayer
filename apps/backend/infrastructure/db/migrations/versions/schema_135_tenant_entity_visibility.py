"""Tenant visibility on workspaces/dashboards plus the grant table that backs it.

Adds the storage for tenant-owned workspaces and dashboards. This revision is
schema only: every default is the value that reproduces today's behaviour, so
applying it changes nothing until the resolver grows a tenant branch.

Two columns answering two different questions
-------------------------------------------
``visibility`` answers *who may see this entity at all*: ``private`` (owner and
the existing share paths, i.e. today) or ``tenant``. It lives on the entity so
the "Mine vs Company" list filter is one indexed column and never a join.

``tenant_entity_grants`` answers *what may each tenant role do with it*: a row
per (entity, tenant, role) granting view/edit/manage. ``owned`` is deliberately
not grantable — it means pure ownership and cannot be handed out.

Three rules the shape of this schema encodes
------------------------------------------
1. ``private`` wins outright. Grants are not consulted for a private entity, so
   a grant row left behind by a visibility flip back to private grants nothing.
   The fail-safe direction for a security switch is the one that reads as "no".

2. Grants are looked up by the *entity's* ``tenant_id``, never the actor's.
   Keying on the actor's tenant would let a company B admin write
   ``(workspace, <company A workspace id>, tenant B, tenant_member, view)`` and
   read company A's workspace through their own tenant. Keyed on the entity's
   tenant that row can never match, so the row is inert regardless of who wrote
   it. The write path must still validate the grant against the actor's admin
   scope; this is the second lock, not a substitute for the first.

3. ``tenant_admin`` and ``tenant_owner`` get ``manage`` implicitly on a
   tenant-visible entity. ``tenant_member`` gets nothing without an explicit
   grant row. So a grant row with ``min_role='tenant_member'`` is how a member
   ever sees a tenant entity, and no grant row is needed to keep the delegated
   admin able to work.

Polymorphic ``entity_id`` has no FK
----------------------------------
``entity_id`` points at ``project_workspaces`` or ``user_dashboards`` depending
on ``entity_type``, so it cannot carry a referential constraint and grant rows
outlive the entity they name. That is inert rather than dangerous: the resolver
loads the entity first, so a row naming a deleted entity matches nothing, and
UUID reuse is not a practical concern. The entity delete path should still clean
its own grant rows up rather than leave them accumulating.
"""

from __future__ import annotations

from alembic import op

revision = "schema_135"
down_revision = "schema_134"
branch_labels = None
depends_on = None


_VISIBILITY_VALUES = "('private', 'tenant')"
_GRANT_TABLE = "tenant_entity_grants"


def upgrade() -> None:
    for table in ("project_workspaces", "user_dashboards"):
        op.execute(
            f"""
            ALTER TABLE {table}
              ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';
            """
        )
        op.execute(
            f"""
            ALTER TABLE {table}
              ADD CONSTRAINT {table}_visibility_check
              CHECK (visibility IN {_VISIBILITY_VALUES});
            """
        )
        op.execute(
            f"""
            COMMENT ON COLUMN {table}.visibility IS
              'private = owner and existing share paths only. tenant = visible '
              'inside the owning tenant; what each role may do there comes from '
              'tenant_entity_grants, except tenant_admin/tenant_owner which get '
              'manage implicitly. Grants are ignored while this is private.';
            """
        )

    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_GRANT_TABLE} (
          entity_type TEXT NOT NULL CHECK (entity_type IN ('workspace', 'dashboard')),
          entity_id UUID NOT NULL,
          tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
          min_role TEXT NOT NULL
            CHECK (min_role IN ('tenant_member', 'tenant_admin', 'tenant_owner')),
          access TEXT NOT NULL CHECK (access IN ('view', 'edit', 'manage')),
          created_by UUID NULL REFERENCES users(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (entity_type, entity_id, tenant_id, min_role)
        );
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_{_GRANT_TABLE}_tenant_type
          ON {_GRANT_TABLE} (tenant_id, entity_type);
        """
    )
    op.execute(
        f"""
        COMMENT ON TABLE {_GRANT_TABLE} IS
          'What a tenant role may do with one tenant-visible workspace or '
          'dashboard. Read keyed on the entity''s own tenant_id, never the '
          'actor''s, so a row cannot bridge two tenants. Not consulted at all '
          'while the entity''s visibility is private. tenant_admin and '
          'tenant_owner hold manage implicitly and need no row here.';
        """
    )


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {_GRANT_TABLE};")
    for table in ("project_workspaces", "user_dashboards"):
        op.execute(
            f"""
            ALTER TABLE {table}
              DROP CONSTRAINT IF EXISTS {table}_visibility_check;
            """
        )
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS visibility;")
