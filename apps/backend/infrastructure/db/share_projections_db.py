"""Persistence for owner-published share projections (ADR 0014 step 6).

Implements the ``ShareProjectionStore`` port from
``apps.backend.domain.shares.projections``. The domain never sees this
module; the service that registers it does.

Every read here is keyed on the **owner**. There is deliberately no
by-grantee lookup, because a lookup path that accepts a grantee id is a
lookup path where someone can eventually be talked into passing the wrong
one. Authorization happens above; this layer only answers "what did this
owner publish".
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db.db import pool

_TABLE = "share_projections"


def _payload(raw: Any) -> dict[str, Any]:
    """Normalise the JSONB column.

    The driver hands back a dict for JSONB, but a row written by an older
    path or a manual insert can arrive as a string, and a projection that
    silently reads as empty is worse than one that fails loudly upstream.
    """
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def projection_get(
    *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT owner_user_id, resource_type, resource_identifier,
                       projection_kind, payload, generated_at, expires_at
                FROM {_TABLE}
                WHERE owner_user_id = %s
                  AND resource_type = %s
                  AND resource_identifier = %s
                LIMIT 1
                """,
                (owner_user_id, resource_type, resource_identifier),
            )
            row = cur.fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = _payload(out.get("payload"))
    return out


def projection_upsert(
    *,
    owner_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
    kind: str,
    payload: dict[str, Any],
    expires_at: datetime,
) -> None:
    """Replace the owner's projection for one resource.

    A single upsert rather than read-modify-write: two publishes racing must
    not interleave into a payload that is half one narrowing and half the
    other.
    """
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_TABLE}
                    (owner_user_id, resource_type, resource_identifier,
                     projection_kind, payload, generated_at, expires_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, now(), %s)
                ON CONFLICT (owner_user_id, resource_type, resource_identifier)
                DO UPDATE SET
                    projection_kind = EXCLUDED.projection_kind,
                    payload = EXCLUDED.payload,
                    generated_at = now(),
                    expires_at = EXCLUDED.expires_at
                """,
                (
                    owner_user_id,
                    resource_type,
                    resource_identifier,
                    kind,
                    json.dumps(payload),
                    expires_at,
                ),
            )
        conn.commit()


def projection_delete_cursor(
    cur: Any,
    *,
    owner_user_id: uuid.UUID,
    resource_type: str,
    resource_identifier: str,
) -> int:
    """Delete on a cursor the caller owns.

    This exists so the revoke cascade can delete inside *its* transaction.
    A cascade that opens its own connection commits ahead of the revoke it
    is cascading from, which is worse than no cascade: if the revoke then
    rolls back, the projection is gone while the grant survives.
    """
    cur.execute(
        f"""
        DELETE FROM {_TABLE}
        WHERE owner_user_id = %s
          AND resource_type = %s
          AND resource_identifier = %s
        """,
        (owner_user_id, resource_type, resource_identifier),
    )
    return int(cur.rowcount or 0)


def projection_delete(
    *, owner_user_id: uuid.UUID, resource_type: str, resource_identifier: str
) -> int:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            deleted = projection_delete_cursor(
                cur,
                owner_user_id=owner_user_id,
                resource_type=resource_type,
                resource_identifier=resource_identifier,
            )
        conn.commit()
    return deleted


def projection_delete_expired(*, limit: int = 200) -> int:
    """Bulk-remove projections past their freshness bound.

    Bounded by ``limit`` because this runs on a timer: an unbounded delete
    on a table that happens to be large would hold a write lock for as long
    as it takes, and this is a janitor, not a migration.
    """
    try:
        capped = max(1, min(int(limit), 5000))
    except (TypeError, ValueError):
        capped = 200
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {_TABLE}
                WHERE (owner_user_id, resource_type, resource_identifier) IN (
                    SELECT owner_user_id, resource_type, resource_identifier
                    FROM {_TABLE}
                    WHERE expires_at <= now()
                    LIMIT {capped}
                )
                """
            )
            deleted = cur.rowcount
        conn.commit()
    return int(deleted or 0)
