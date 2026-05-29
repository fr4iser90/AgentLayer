"""
Share Permissions Database Layer

Granular permission system who can access what from whom.
Separates technical connections from social permissions.
"""
from __future__ import annotations

import uuid
from typing import Any
from psycopg.rows import dict_row

from apps.backend.infrastructure.db.db import pool

# Canonical ids — must match SharesSettings RESOURCE_TYPES in the frontend.
SHARE_RESOURCE_GOOGLE_CALENDAR = "google_calendar"
SHARE_RESOURCE_GITHUB_ACTIVITY = "github_activity"
SHARE_RESOURCE_TODOIST = "todoist"
SHARE_RESOURCE_NOTES = "notes"
SHARE_RESOURCE_ROADMAP = "roadmap"

SHARE_RESOURCE_ALIASES: dict[str, tuple[str, ...]] = {
    SHARE_RESOURCE_GOOGLE_CALENDAR: ("calendar",),
}


def _resource_type_variants(resource_type: str) -> tuple[str, ...]:
    canonical = (resource_type or "").strip().lower()
    if not canonical:
        return ()
    aliases = SHARE_RESOURCE_ALIASES.get(canonical, ())
    out: list[str] = []
    for candidate in (canonical, *aliases):
        if candidate and candidate not in out:
            out.append(candidate)
    return tuple(out)


def share_permission_set(
    *,
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
    allowed: bool = True
) -> bool:
    """
    Set or remove share permission for a specific user and resource type.
    
    resource_type examples: 'google_calendar', 'github_activity', 'todoist', 'notes', 'roadmap'
    """
    ok = False
    
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if allowed:
                cur.execute(
                    """
                    INSERT INTO share_permissions
                      (owner_user_id, grantee_user_id, resource_type, resource_identifier, is_allowed, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, now(), now())
                    ON CONFLICT (owner_user_id, grantee_user_id, resource_type, resource_identifier) DO UPDATE
                    SET updated_at = now(), revoked_at = NULL, is_allowed = EXCLUDED.is_allowed
                    """,
                    (
                        owner_user_id, 
                        grantee_user_id, 
                        resource_type.strip().lower(),
                        resource_identifier.strip().lower(),
                        allowed
                    )
                )
            else:
                cur.execute(
                    """
                    UPDATE share_permissions
                    SET revoked_at = now(), updated_at = now(), is_allowed = %s
                    WHERE owner_user_id = %s
                      AND grantee_user_id = %s
                      AND resource_type = %s
                      AND resource_identifier = %s
                    """,
                    (
                        allowed,
                        owner_user_id, 
                        grantee_user_id, 
                        resource_type.strip().lower(),
                        resource_identifier.strip().lower()
                    )
                )
            
            ok = cur.rowcount > 0
        conn.commit()
    
    return ok


def share_permission_check(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> bool:
    """Check if grantee has active permission to access owner's resource."""
    return share_permission_check_resolved(
        owner_user_id=owner_user_id,
        grantee_user_id=grantee_user_id,
        resource_type=resource_type,
        resource_identifier=resource_identifier,
    )


def share_permission_check_resolved(
    owner_user_id: uuid.UUID,
    grantee_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str = "primary",
) -> bool:
    """Check permission using canonical resource_type plus known legacy aliases."""
    variants = _resource_type_variants(resource_type)
    if not variants:
        return False
    identifier = (resource_identifier or "primary").strip().lower()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM share_permissions
                WHERE owner_user_id = %s
                  AND grantee_user_id = %s
                  AND resource_type = ANY(%s)
                  AND resource_identifier = %s
                  AND revoked_at IS NULL
                  AND is_allowed = TRUE
                LIMIT 1
                """,
                (owner_user_id, grantee_user_id, list(variants), identifier),
            )
            return cur.fetchone() is not None


def list_shares_by_owner(owner_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all outgoing shares from this user."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type, sp.resource_identifier, sp.grantee_user_id, sp.created_at,
                       u.email, u.display_name
                FROM share_permissions sp
                JOIN users u ON sp.grantee_user_id = u.id
                WHERE sp.owner_user_id = %s
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                ORDER BY sp.resource_type, u.display_name
                """,
                (owner_user_id,)
            )
            rows = cur.fetchall()
    
    return [dict(r) for r in rows]


def list_shares_by_grantee(grantee_user_id: uuid.UUID) -> list[dict[str, Any]]:
    """List all incoming shares this user has access to."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT sp.resource_type, sp.resource_identifier, sp.owner_user_id, sp.created_at,
                       u.email, u.display_name
                FROM share_permissions sp
                JOIN users u ON sp.owner_user_id = u.id
                WHERE sp.grantee_user_id = %s
                  AND sp.revoked_at IS NULL
                  AND sp.is_allowed = TRUE
                ORDER BY sp.resource_type, u.display_name
                """,
                (grantee_user_id,)
            )
            rows = cur.fetchall()
    
    return [dict(r) for r in rows]


def list_shares_between(user_id_1: uuid.UUID, user_id_2: uuid.UUID) -> dict[str, Any]:
    """Get bidirectional share status between two users."""
    outgoing = []
    incoming = []
    
    outgoing_shares = list_shares_by_owner(user_id_1)
    for s in outgoing_shares:
        if s["grantee_user_id"] == user_id_2:
            outgoing.append(s["resource_type"])
    
    incoming_shares = list_shares_by_grantee(user_id_1)
    for s in incoming_shares:
        if s["owner_user_id"] == user_id_2:
            incoming.append(s["resource_type"])
    
    return {
        "outgoing": outgoing,
        "incoming": incoming
    }