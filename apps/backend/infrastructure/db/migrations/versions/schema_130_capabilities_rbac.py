"""P6 (Weg B): per-user admin capabilities + cumulative profession roles.

- ``users.capabilities`` JSONB: global platform/admin capabilities
  (``agent.assign``, ``user.manage``, ...). Site admin implicitly holds all.
- ``tenant_profession_roles.capabilities`` JSONB: authoritative content RBAC
  source, seeded from the legacy ``role_kind`` CHECK value. ``role_kind`` stays
  a display/legacy label; the CHECK is dissolved.
- ``user_profession_assignments`` gets a surrogate ``id`` PK + a three-column
  unique constraint so a user may hold multiple (cumulative) roles per tenant.
"""

from __future__ import annotations

from alembic import op

revision = "schema_130"
down_revision = "schema_129"
branch_labels = None
depends_on = None


# role_kind -> JSONB capabilities array (mirrors ``_KIND_CAPABILITIES``).
_KIND_TO_CAPS: dict[str, str] = {
    "content_editor": '["knowledge.search", "content.editor"]',
    "content_reviewer": '["knowledge.search", "content.editor", "content.review"]',
    "content_approver": '["knowledge.search", "content.editor", "content.publish"]',
    "domain_admin": '["knowledge.search", "content.editor", "content.review", "content.publish", "profession.admin"]',
    "end_user": '["knowledge.search"]',
    "trainee": '["knowledge.search"]',
}


def upgrade() -> None:
    # --- Platform/admin capabilities on users (cumulative) ---
    op.execute(
        """
        ALTER TABLE users
          ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )

    # --- Authoritative content capabilities on roles ---
    op.execute(
        """
        ALTER TABLE tenant_profession_roles
          ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )
    # Seed capabilities from the legacy role_kind value (deterministic, idempotent).
    for kind, caps in _KIND_TO_CAPS.items():
        op.execute(
            f"UPDATE tenant_profession_roles SET capabilities = {caps}::jsonb WHERE role_kind = '{kind}'"
        )

    # Dissolve the role_kind CHECK; role_kind becomes a free-form label.
    op.execute("ALTER TABLE tenant_profession_roles DROP CONSTRAINT IF EXISTS tenant_profession_roles_kind_check")
    op.execute("ALTER TABLE tenant_profession_roles ALTER COLUMN role_kind DROP DEFAULT")

    # --- Cumulative roles: surrogate PK + three-column uniqueness ---
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          ADD COLUMN IF NOT EXISTS id BIGSERIAL
        """
    )
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          DROP CONSTRAINT IF EXISTS user_profession_assignments_pkey
        """
    )
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          ADD PRIMARY KEY (id)
        """
    )
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          ADD CONSTRAINT uq_user_tenant_role UNIQUE (user_id, tenant_id, profession_role_id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          DROP CONSTRAINT IF EXISTS uq_user_tenant_role
        """
    )
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          DROP CONSTRAINT IF EXISTS user_profession_assignments_pkey
        """
    )
    op.execute("ALTER TABLE user_profession_assignments DROP COLUMN IF EXISTS id")
    op.execute(
        """
        ALTER TABLE user_profession_assignments
          ADD PRIMARY KEY (user_id, tenant_id)
        """
    )

    op.execute("ALTER TABLE tenant_profession_roles ADD COLUMN IF NOT EXISTS role_kind VARCHAR(32) NOT NULL DEFAULT 'end_user'")
    for kind in _KIND_TO_CAPS:
        op.execute(f"UPDATE tenant_profession_roles SET role_kind = '{kind}' WHERE capabilities @> {_KIND_TO_CAPS[kind]}::jsonb")
    op.execute(
        """
        ALTER TABLE tenant_profession_roles
          ADD CONSTRAINT tenant_profession_roles_kind_check
            CHECK (role_kind IN (
              'content_editor', 'content_reviewer', 'content_approver',
              'domain_admin', 'end_user', 'trainee'
            ))
        """
    )
    op.execute("ALTER TABLE tenant_profession_roles DROP COLUMN IF EXISTS capabilities")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS capabilities")
