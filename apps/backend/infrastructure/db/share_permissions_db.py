"""
Share Permissions Database Layer

Granular permission system who can access what from whom.
Separates technical connections from social permissions.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.domain.shares.policy import grant_is_active
from apps.backend.infrastructure.db.db import pool

# Canonical ids — kept for backward compatibility with imports/tests.
SHARE_RESOURCE_GOOGLE_CALENDAR = "google_calendar"
SHARE_RESOURCE_GITHUB_ACTIVITY = "github_activity"
SHARE_RESOURCE_TODOIST = "todoist"
SHARE_RESOURCE_NOTES = "notes"
SHARE_RESOURCE_ROADMAP = "roadmap"
SHARE_RESOURCE_DASHBOARD = "dashboard"
SHARE_RESOURCE_COLLECTION = "collection"

SHARE_RESOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    SHARE_RESOURCE_GOOGLE_CALENDAR: ("calendar",),
    SHARE_RESOURCE_DASHBOARD: ("board",),
    SHARE_RESOURCE_COLLECTION: ("pets", "haustier", "haustiere", "pet", "data"),
}


def _resource_type_variants(resource_type: str) -> tuple[str, ...]:
    """Canonical id plus legacy DB aliases (backward compat for old grant rows)."""
    from apps.backend.domain.shares.catalog import canonical_resource_type

    canonical = canonical_resource_type(resource_type) or (resource_type or "").strip().lower()
    if not canonical:
        return ()
    aliases = SHARE_RESOURCE_ALIASES.get(canonical, ())
    out: list[str] = []
    for candidate in (canonical, *aliases):
        if candidate and candidate not in out:
            out.append(candidate)
    return tuple(out)


def _row_policy(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _serialize_grant(row: dict[str, Any]) -> dict[str, Any]:
    policy = _row_policy(row.get("policy"))
    return {
        "resource_type": row.get("resource_type"),
        "resource_identifier": row.get("resource_identifier") or "primary",
        "policy": policy,
        "created_at": row.get("created_at"),
        "grantee_user_id": row.get("grantee_user_id"),
        "owner_user_id": row.get("owner_user_id"),
        "email": row.get("email"),
        "display_name": row.get("display_name"),
        "active": grant_is_active(
            is_allowed=bool(row.get("is_allowed")),
            revoked_at=row.get("revoked_at"),
            policy=policy,
        ),
    }


def _canonical(resource_type: str) -> str:
    from apps.backend.domain.shares.catalog import canonical_resource_type

    return (
        canonical_resource_type(resource_type)
        or (resource_type or "").strip().lower()
    )


def count_active_grants(
    owner_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> int:
    """How many live grants still name this owner's resource.

    Counted across the canonical id *and* its legacy aliases, because a
    projection is keyed canonically while grants are stored under whatever
    name was written. Counting only the canonical id would report zero
    while a ``calendar`` grant is still live, and the cascade would delete
    a projection somebody can still read.
    """
    variants = _resource_type_variants(resource_type)
    if not variants:
        return 0
    identifier = (resource_identifier or "primary").strip().lower()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT is_allowed, revoked_at, policy
                FROM share_permissions
                WHERE owner_user_id = %s
                  AND resource_type = ANY(%s)
                  AND resource_identifier = %s
                  AND revoked_at IS NULL
                  AND is_allowed = TRUE
                """,
                (owner_user_id, list(variants), identifier),
            )
            rows = cur.fetchall()
    return sum(
        1
        for r in rows
        if grant_is_active(
            is_allowed=True, revoked_at=r.get("revoked_at"), policy=_row_policy(r.get("policy"))
        )
    )


def share_permission_set(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
    allowed: bool = True,
    *,
    policy: dict[str, Any] | None = None,
) -> bool:
    """
    Set or remove share permission for a specific user and resource type.

    resource_type examples: 'google_calendar', 'github_activity', 'todoist', 'notes', 'roadmap'
    """
    rt = resource_type.strip().lower()
    ident = (resource_identifier or "primary").strip().lower()
    pol = policy if isinstance(policy, dict) else {}

    with pool().connection() as conn:
        with conn.cursor() as cur:
            if allowed:
                cur.execute(
                    """
                    INSERT INTO share_permissions
                      (owner_user_id, grantee_user_id, resource_type, resource_identifier,
                       is_allowed, policy, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, now(), now())
                    ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier)
                    DO UPDATE SET
                      updated_at = now(),
                      revoked_at = NULL,
                      is_allowed = EXCLUDED.is_allowed,
                      policy = EXCLUDED.policy
                    """,
                    (
                        owner_user_id,
                        grantee_user_id,
                        rt,
                        ident,
                        True,
                        json.dumps(pol),
                    ),
                )
                ok = cur.rowcount > 0
            else:
                cur.execute(
                    """
                    UPDATE share_permissions
                    SET revoked_at = now(), updated_at = now(), is_allowed = FALSE
                    WHERE owner_user_id = %s
                      AND grantee_user_id = %s
                      AND resource_type = %s
                      AND resource_identifier = %s
                      AND revoked_at IS NULL
                    """,
                    (owner_user_id, grantee_user_id, rt, ident),
                )
                ok = True
                # The cascade runs in the same transaction as the revoke,
                # not afterwards. A delete that happens later leaves a
                # window where the grant is gone and the owner's published
                # view is still standing, and "it gets cleaned up soon" is
                # exactly the kind of guarantee this ADR was written
                # because it kept not holding.
                cur.execute(
                    """
                    SELECT policy
                    FROM share_permissions
                    WHERE owner_user_id = %s
                      AND resource_type = ANY(%s)
                      AND resource_identifier = %s
                      AND revoked_at IS NULL
                      AND is_allowed = TRUE
                    """,
                    (owner_user_id, list(_resource_type_variants(rt)), ident),
                )
                still_live = 0
                for r in cur.fetchall():
                    # This cursor is a plain tuple cursor, not dict_row, so
                    # the single selected column comes back positionally.
                    # Handle both rather than assume which factory is set.
                    raw = r["policy"] if isinstance(r, dict) else r[0]
                    if grant_is_active(
                        is_allowed=True,
                        revoked_at=None,
                        policy=_row_policy(raw),
                    ):
                        still_live += 1
                if still_live == 0:
                    from apps.backend.infrastructure.db.share_projections_db import (
                        projection_delete_cursor,
                    )

                    projection_delete_cursor(
                        cur,
                        owner_user_id=owner_user_id,
                        resource_type=_canonical(rt),
                        resource_identifier=ident,
                    )
        conn.commit()

    return ok


def share_permission_get(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> dict[str, Any] | None:
    """Return active grant row including policy, or None."""
    variants = _resource_type_variants(resource_type)
    if not variants:
        return None
    identifier = (resource_identifier or "primary").strip().lower()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT owner_user_id, grantee_user_id, resource_type, resource_identifier,
                       is_allowed, policy, revoked_at, created_at, updated_at
                FROM share_permissions
                WHERE owner_user_id = %s
                  AND grantee_user_id = %s
                  AND resource_type = ANY(%s)
                  AND resource_identifier = %s
                  AND revoked_at IS NULL
                  AND is_allowed = TRUE
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (owner_user_id, grantee_user_id, list(variants), identifier),
            )
            row = cur.fetchone()
    if not row:
        return None
    policy = _row_policy(row.get("policy"))
    if not grant_is_active(
        is_allowed=bool(row["is_allowed"]),
        revoked_at=row.get("revoked_at"),
        policy=policy,
    ):
        return None
    return {
        "owner_user_id": row["owner_user_id"],
        "grantee_user_id": row["grantee_user_id"],
        "resource_type": row["resource_type"],
        "resource_identifier": row["resource_identifier"],
        "policy": policy,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def share_permission_check(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> bool:
    """Check if grantee has active permission to access owner's resource."""
    return share_permission_get(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    ) is not None


def share_permission_check_resolved(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> bool:
    """Check permission using canonical resource_type plus known legacy aliases."""
    return share_permission_check(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    )


def list_shares_by_owner(owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all outgoing shares from this user."""
    # tenant-scope: guarded owner_user_id — a friend share is a pair of
    # users, not a pair of tenants, and this enumerates one party's own
    # outgoing grants. Same boundary friends_db uses; tenancy is not what
    # confines these rows, the caller's own identity is.
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type, sp.resource_identifier, sp.policy,
                       sp.grantee_user_id, sp.created_at, sp.is_allowed, sp.revoked_at,
                       u.email, u.display_name
                FROM share_permissions sp
                JOIN users u ON sp.grantee_user_id = u.id
                WHERE sp.owner_user_id = %s
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                ORDER BY sp.resource_type, u.display_name
                """,
                (owner_user_id,),
            )
            rows = cur.fetchall()

    grants = [_serialize_grant(dict(r)) for r in rows]
    return [g for g in grants if g.get("active")]


def list_shares_by_grantee(grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all incoming shares this user has access to."""
    # tenant-scope: guarded grantee_user_id — mirror of the above, keyed to
    # the other side of the pair.
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type, sp.resource_identifier, sp.policy,
                       sp.owner_user_id, sp.created_at, sp.is_allowed, sp.revoked_at,
                       u.email, u.display_name
                FROM share_permissions sp
                JOIN users u ON sp.owner_user_id = u.id
                WHERE sp.grantee_user_id = %s
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                ORDER BY sp.resource_type, u.display_name
                """,
                (grantee_user_id,),
            )
            rows = cur.fetchall()

    grants = [_serialize_grant(dict(r)) for r in rows]
    return [g for g in grants if g.get("active")]


def list_shares_between(user_id_1: uuid.UUID, user_id_2: uuid.UUID) -> dict[str, Any]:
    """Get bidirectional share status between two users."""
    outgoing_grants: list[dict[str, Any]] = []
    incoming_grants: list[dict[str, Any]] = []

    for s in list_shares_by_owner(user_id_1):
        if s.get("grantee_user_id") == user_id_2:
            outgoing_grants.append(s)

    for s in list_shares_by_grantee(user_id_1):
        if s.get("owner_user_id") == user_id_2:
            incoming_grants.append(s)

    return {
        "outgoing": [g["resource_type"] for g in outgoing_grants],
        "incoming": [g["resource_type"] for g in incoming_grants],
        "outgoing_grants": outgoing_grants,
        "incoming_grants": incoming_grants,
    }
