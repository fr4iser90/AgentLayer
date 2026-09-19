"""Writing the ``tenant_entity_grants`` rows the access resolver reads.

The resolver keys its grant lookup on the **entity's** tenant, which makes a
grant row written against the wrong tenant inert. That is the second lock. It
does not stop the attack that matters here: a company B admin writing a row
that names company **A**'s tenant and one of A's workspaces. That row matches
A's members legitimately, and the reader's keying cannot tell it apart from a
row A's own admin wrote.

So this module refuses a (entity, tenant) pair that does not agree. The tenant
is read back from the entity row and compared against what the caller asked to
write; a caller that passes a request-supplied tenant gets an error rather than
a cross-company grant. The handler still has to check the entity's tenant
against the actor's admin scope -- this only guarantees the row is internally
consistent.

Grants are upserts on the primary key (entity_type, entity_id, tenant_id,
min_role), so one minimum role carries exactly one access level. Re-raising a
grant with a higher level replaces it rather than adding a second row.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.access.entity_access import (
    GRANT_ACCESS_LEVELS,
    GRANT_MIN_ROLES,
)
from apps.backend.infrastructure.access.entity_access_service import (
    DASHBOARD,
    SUPPORTED_ENTITY_TYPES,
    WORKSPACE,
)


class GrantError(ValueError):
    """The grant cannot be written. Reason is in the message."""


def _check_shape(entity_type: str, min_role: str, access: str) -> tuple[str, str, str]:
    et = str(entity_type or "").strip().lower()
    mr = str(min_role or "").strip().lower()
    ac = str(access or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise GrantError(f"unsupported entity type: {entity_type}")
    if mr not in GRANT_MIN_ROLES:
        raise GrantError(
            f"min_role must be one of {', '.join(GRANT_MIN_ROLES)}; got {min_role!r}"
        )
    if ac not in GRANT_ACCESS_LEVELS:
        raise GrantError(
            f"access must be one of {', '.join(GRANT_ACCESS_LEVELS)}; got {access!r}"
        )
    return et, mr, ac


def _assert_entity_in_tenant(
    cur: Any, entity_type: str, entity_id: str, tenant_id: int
) -> None:
    """Refuse unless the entity exists and belongs to ``tenant_id``.

    This is the check that makes a mismatched (entity, tenant) pair unwritable
    no matter how the caller obtained the tenant.
    """
    table = "project_workspaces" if entity_type == WORKSPACE else "user_dashboards"
    # tenant-scope: guarded — the fetched tenant_id is compared against the
    # requested grant tenant below, so a row for another company cannot be written.
    cur.execute(f"SELECT tenant_id FROM {table} WHERE id = %s", (entity_id,))  # noqa: S608
    row = cur.fetchone()
    if row is None:
        raise GrantError(f"{entity_type} not found: {entity_id}")
    if int(row[0]) != int(tenant_id):
        raise GrantError(
            f"the {entity_type} belongs to tenant {int(row[0])}, not {int(tenant_id)}; "
            "grants are keyed on the entity's own tenant"
        )


def entity_tenant(entity_type: str, entity_id: str) -> int | None:
    """The owning tenant of a grantable entity, or None if it does not exist.

    A handler resolves the tenant here rather than taking it from the request, so
    the tenant in a grant row always comes from the entity itself. The writer
    re-checks the same fact; this is the read that lets the caller apply its
    admin-scope check first.
    """
    et = str(entity_type or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise GrantError(f"unsupported entity type: {entity_type}")

    from apps.backend.infrastructure.db import db

    table = "project_workspaces" if et == WORKSPACE else "user_dashboards"
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            # tenant-scope: guarded — the value returned is the tenant being
            # resolved, and the caller must check it against its admin scope.
            cur.execute(f"SELECT tenant_id FROM {table} WHERE id = %s", (entity_id,))  # noqa: S608
            row = cur.fetchone()
    if row is None:
        return None
    return int(row[0])


def list_grants(
    entity_type: str, entity_id: str, tenant_id: int
) -> list[dict[str, Any]]:
    """Every grant on one entity, as written."""
    et = str(entity_type or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise GrantError(f"unsupported entity type: {entity_type}")

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT min_role, access, created_by, created_at
                  FROM tenant_entity_grants
                 WHERE entity_type = %s AND entity_id = %s AND tenant_id = %s
                 ORDER BY min_role, access
                """,
                (et, entity_id, int(tenant_id)),
            )
            rows = list(cur.fetchall())
    return [
        {
            "min_role": r[0],
            "access": r[1],
            "created_by": str(r[2]) if r[2] else None,
            "created_at": r[3].isoformat() if r[3] else None,
        }
        for r in rows
    ]


def upsert_grant(
    *,
    entity_type: str,
    entity_id: str,
    tenant_id: int,
    min_role: str,
    access: str,
    created_by: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Add or replace one grant.

    ``tenant_id`` must be the entity's own tenant. It is verified against the
    entity row rather than trusted, so a caller that forwards a tenant from a
    request cannot land a grant in a company it does not own.
    """
    et, mr, ac = _check_shape(entity_type, min_role, access)

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            _assert_entity_in_tenant(cur, et, entity_id, tenant_id)
            cur.execute(
                """
                INSERT INTO tenant_entity_grants
                  (entity_type, entity_id, tenant_id, min_role, access, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (entity_type, entity_id, tenant_id, min_role)
                DO UPDATE SET access = EXCLUDED.access,
                            created_by = EXCLUDED.created_by,
                            created_at = now()
                """,
                (et, entity_id, int(tenant_id), mr, ac, created_by),
            )
        conn.commit()

    return {
        "entity_type": et,
        "entity_id": str(entity_id),
        "tenant_id": int(tenant_id),
        "min_role": mr,
        "access": ac,
    }


def revoke_grant(
    *, entity_type: str, entity_id: str, tenant_id: int, min_role: str
) -> bool:
    """Remove the grant for one minimum role. True if a row was deleted."""
    et = str(entity_type or "").strip().lower()
    mr = str(min_role or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise GrantError(f"unsupported entity type: {entity_type}")
    if mr not in GRANT_MIN_ROLES:
        raise GrantError(
            f"min_role must be one of {', '.join(GRANT_MIN_ROLES)}; got {min_role!r}"
        )

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM tenant_entity_grants
                 WHERE entity_type = %s AND entity_id = %s
                   AND tenant_id = %s AND min_role = %s
                """,
                (et, entity_id, int(tenant_id), mr),
            )
            deleted = int(getattr(cur, "rowcount", 0) or 0)
        conn.commit()
    return deleted > 0


def replace_grants(
    *,
    entity_type: str,
    entity_id: str,
    tenant_id: int,
    grants: list[dict[str, Any]],
    created_by: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Set the whole grant set for one entity, in one transaction.

    Replacing rather than patching, because a partially-applied grant set is a
    security surface nobody can reason about: the caller states the complete
    intended set and either all of it lands or none does.
    """
    et = str(entity_type or "").strip().lower()
    if et not in SUPPORTED_ENTITY_TYPES:
        raise GrantError(f"unsupported entity type: {entity_type}")

    seen: set[str] = set()
    staged: list[tuple[str, str]] = []
    for g in grants:
        _et, mr, ac = _check_shape(entity_type, g.get("min_role"), g.get("access"))
        if mr in seen:
            raise GrantError(f"min_role {mr!r} appears more than once in the grant set")
        seen.add(mr)
        staged.append((mr, ac))

    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            _assert_entity_in_tenant(cur, et, entity_id, tenant_id)
            cur.execute(
                """
                DELETE FROM tenant_entity_grants
                 WHERE entity_type = %s AND entity_id = %s AND tenant_id = %s
                """,
                (et, entity_id, int(tenant_id)),
            )
            for mr, ac in staged:
                cur.execute(
                    """
                    INSERT INTO tenant_entity_grants
                      (entity_type, entity_id, tenant_id, min_role, access, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (et, entity_id, int(tenant_id), mr, ac, created_by),
                )
        conn.commit()

    return [
        {
            "entity_type": et,
            "entity_id": str(entity_id),
            "tenant_id": int(tenant_id),
            "min_role": mr,
            "access": ac,
        }
        for mr, ac in staged
    ]
