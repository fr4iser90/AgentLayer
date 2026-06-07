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

from apps.backend.domain.shares.catalog import resource_type_variants
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
    variants = resource_type_variants(resource_type)
    if variants:
        return variants
    canonical = (resource_type or "").strip().lower()
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
