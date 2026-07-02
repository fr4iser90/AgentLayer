from __future__ import annotations

import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db.db import pool


def kb_note_is_owner(note_id: int, user_id: uuid.UUID, tenant_id: int) -> bool:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM user_kb_notes
                WHERE id = %s AND user_id = %s AND tenant_id = %s
                """,
                (note_id, user_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def kb_note_share_create(
    note_id: int,
    owner_user_id: uuid.UUID,
    tenant_id: int,
    grantee_user_id: uuid.UUID,
) -> int:
    if grantee_user_id == owner_user_id:
        raise ValueError("cannot share a note with yourself")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, tenant_id FROM user_kb_notes WHERE id = %s",
                (note_id,),
            )
            nrow = cur.fetchone()
            if not nrow:
                raise ValueError("note not found")
            nu, nt = nrow[0], int(nrow[1])
            ou = nu if isinstance(nu, uuid.UUID) else uuid.UUID(str(nu))
            if ou != owner_user_id or nt != tenant_id:
                raise ValueError("not the owner of this note")
            cur.execute(
                "SELECT tenant_id FROM users WHERE id = %s",
                (grantee_user_id,),
            )
            grow = cur.fetchone()
            if not grow or int(grow[0]) != tenant_id:
                raise ValueError("grantee not in the same tenant")
            cur.execute(
                """
                INSERT INTO user_kb_note_shares (note_id, grantee_user_id)
                VALUES (%s, %s)
                ON CONFLICT (note_id, grantee_user_id) DO NOTHING
                RETURNING id
                """,
                (note_id, grantee_user_id),
            )
            ins = cur.fetchone()
            if not ins:
                raise ValueError("this user already has access")
            sid = int(ins[0])
        conn.commit()
    return sid


def kb_note_share_list(
    note_id: int, owner_user_id: uuid.UUID, tenant_id: int
) -> list[dict[str, Any]]:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT s.id, s.grantee_user_id, s.created_at, u.email, u.external_sub
                FROM user_kb_note_shares s
                JOIN user_kb_notes n ON n.id = s.note_id
                JOIN users u ON u.id = s.grantee_user_id
                WHERE s.note_id = %s AND n.user_id = %s AND n.tenant_id = %s
                ORDER BY s.created_at DESC
                """,
                (note_id, owner_user_id, tenant_id),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        gid = r["grantee_user_id"]
        out.append(
            {
                "share_id": int(r["id"]),
                "grantee_user_id": str(gid),
                "grantee_email": r.get("email"),
                "grantee_external_sub": r.get("external_sub"),
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
        )
    return out


def kb_note_share_delete(share_id: int, owner_user_id: uuid.UUID, tenant_id: int) -> bool:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_kb_note_shares s
                USING user_kb_notes n
                WHERE s.id = %s AND s.note_id = n.id
                  AND n.user_id = %s AND n.tenant_id = %s
                RETURNING s.id
                """,
                (share_id, owner_user_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None
