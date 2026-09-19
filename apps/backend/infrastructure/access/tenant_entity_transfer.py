"""Ownership transfer for tenant-visible entities, and the blockers it clears.

``move_user_tenant`` refuses to move a person who still owns tenant-visible
workspaces or dashboards. This module is how an admin unblocks that: hand the
company's entities to another member of the same tenant, then move the person.

The transfer moves ``owner_user_id`` only. The entity's ``tenant_id`` does not
change, and cannot — the target has to be a member of the tenant that already
owns the entity, which is what stops a transfer from being a way to smuggle
data between companies.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.access.tenant_ownership import (
    TenantOwnedEntitiesConflict,
    same_tenant,
)
from apps.backend.infrastructure.access.entity_access_service import (
    DASHBOARD,
    WORKSPACE,
)


class TransferError(ValueError):
    """The transfer cannot be made. Reason is in the message."""


def _count_with(cur: Any, user_id: uuid.UUID) -> tuple[int, int]:
    # tenant-scope: guarded owner_user_id — the count is partitioned by the
    # owner, which is narrower than a tenant filter and is the question asked.
    cur.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM project_workspaces
             WHERE owner_user_id = %s AND visibility = 'tenant'),
          (SELECT COUNT(*) FROM user_dashboards
             WHERE owner_user_id = %s AND visibility = 'tenant')
        """,
        (user_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        return (0, 0)
    return (int(row[0] or 0), int(row[1] or 0))


def count_tenant_owned_entities(user_id: uuid.UUID) -> tuple[int, int]:
    """(workspaces, dashboards) this user owns that are visible to their tenant."""
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            return _count_with(cur, user_id)


def raise_if_owns_tenant_entities(
    user_id: uuid.UUID, cur: Any = None
) -> None:
    """Raise unless the user owns nothing that is visible beyond themselves.

    Pass ``cur`` to count inside a transaction the caller already holds. Opening
    a second connection from here while the caller holds one is how a pool
    deadlock starts.
    """
    if cur is not None:
        workspaces, dashboards = _count_with(cur, user_id)
    else:
        workspaces, dashboards = count_tenant_owned_entities(user_id)
    if workspaces or dashboards:
        raise TenantOwnedEntitiesConflict(user_id, workspaces, dashboards)


def guarded_move_user_tenant(user_id: uuid.UUID, tenant_id: int) -> bool:
    """Move a user between tenants, refusing while they still own company data.

    The policy lives here rather than inside ``db.move_user_tenant`` because it
    is a tenant-ownership question and not plumbing: ``move_user_tenant`` is a
    generic primitive and has to stay that way. The consequence worth knowing is
    that a bare ``db.move_user_tenant`` is the unguarded path — anything that
    moves a person should come through here.

    Raises ``TenantOwnedEntitiesConflict`` before anything is written when the
    user still owns something visible beyond themselves. A move to the tenant
    they are already in is not a move and is never blocked.
    """
    from apps.backend.infrastructure.db import db

    previous = int(db.user_tenant_id(user_id) or 1)
    if previous != int(tenant_id):
        raise_if_owns_tenant_entities(user_id)
    return db.move_user_tenant(user_id, tenant_id)


def _load_entity(cur: Any, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    if entity_type == WORKSPACE:
        cur.execute(
            """
            SELECT id, tenant_id, owner_user_id, name, visibility
            FROM project_workspaces WHERE id = %s
            """,
            (entity_id,),
        )
    else:
        cur.execute(
            """
            SELECT id, tenant_id, owner_user_id, title, visibility
            FROM user_dashboards WHERE id = %s
            """,
            (entity_id,),
        )
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "tenant_id": int(row[1]),
        "owner_user_id": row[2],
        "label": row[3],
        "visibility": str(row[4] or "private").strip().lower(),
    }


def transfer_entity_ownership(
    entity_type: str, entity_id: str, to_user_id: uuid.UUID
) -> dict[str, Any]:
    """Hand ``entity_id`` over to ``to_user_id``, within its current tenant.

    Raises ``TransferError`` when the entity is missing, the target is not in
    the entity's tenant, or the target already owns something of that name
    (workspaces are unique per owner).
    """
    if entity_type not in (WORKSPACE, DASHBOARD):
        raise TransferError(f"unsupported entity type: {entity_type}")

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            entity = _load_entity(cur, entity_type, entity_id)
            if entity is None:
                raise TransferError(f"{entity_type} not found: {entity_id}")

            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (to_user_id,))
            target = cur.fetchone()
            if target is None:
                raise TransferError(f"target user not found: {to_user_id}")
            target_tenant = int(target[0])

            if not same_tenant(entity["tenant_id"], target_tenant):
                raise TransferError(
                    f"target user is in tenant {target_tenant} but the "
                    f"{entity_type} belongs to tenant {entity['tenant_id']}"
                )

            if str(entity["owner_user_id"] or "") == str(to_user_id):
                raise TransferError("target already owns this entity")

            if entity_type == WORKSPACE:
                # tenant-scope: guarded owner_user_id — uniqueness is per owner,
                # which is exactly the collision being tested for.
                cur.execute(
                    "SELECT 1 FROM project_workspaces "
                    "WHERE owner_user_id = %s AND name = %s",
                    (to_user_id, entity["label"]),
                )
                if cur.fetchone() is not None:
                    raise TransferError(
                        f"target already owns a workspace named {entity['label']!r}"
                    )
                cur.execute(
                    "UPDATE project_workspaces "
                    "SET owner_user_id = %s, access_role = 'owner', "
                    "    updated_at = now() "
                    "WHERE id = %s",
                    (to_user_id, entity_id),
                )
            else:
                cur.execute(
                    "UPDATE user_dashboards "
                    "SET owner_user_id = %s, updated_at = now() "
                    "WHERE id = %s",
                    (to_user_id, entity_id),
                )
        conn.commit()

    return {
        "entity_type": entity_type,
        "entity_id": str(entity["id"]),
        "tenant_id": entity["tenant_id"],
        "previous_owner": str(entity["owner_user_id"]),
        "new_owner": str(to_user_id),
        "visibility": entity["visibility"],
    }


def transfer_all_tenant_entities(
    from_user_id: uuid.UUID, to_user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Hand every tenant-visible entity of one person to another.

    Used to unblock a tenant move in one action. Transfers are committed one at
    a time, so a failure partway leaves the rest still to move rather than
    rolling back what already succeeded — the caller reports what got through.
    """
    from apps.backend.infrastructure.db import db

    moved: list[dict[str, Any]] = []
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            ids: list[tuple[str, str]] = []
            cur.execute(
                """
                SELECT 'workspace', id::text FROM project_workspaces
                 WHERE owner_user_id = %s AND visibility = 'tenant'
                """,
                (from_user_id,),
            )
            # tenant-scope: guarded owner_user_id — enumerating one owner's rows.
            ids.extend((str(r[0]), str(r[1])) for r in cur.fetchall())
            cur.execute(
                """
                SELECT 'dashboard', id::text FROM user_dashboards
                 WHERE owner_user_id = %s AND visibility = 'tenant'
                """,
                (from_user_id,),
            )
            ids.extend((str(r[0]), str(r[1])) for r in cur.fetchall())

    for entity_type, eid in ids:
        moved.append(transfer_entity_ownership(entity_type, eid, to_user_id))
    return moved
