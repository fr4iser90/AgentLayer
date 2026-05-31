"""Persist thumbs up/down feedback on chat assistant turns."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.db import db


def upsert_feedback(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_position: int,
    rating: int,
    comment: str | None = None,
) -> dict[str, Any]:
    if rating not in (-1, 1):
        raise ValueError("rating must be -1 or 1")
    if message_position < 0:
        raise ValueError("message_position must be >= 0")
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_message_feedback
                  (tenant_id, user_id, conversation_id, message_position, rating, comment, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (user_id, conversation_id, message_position)
                DO UPDATE SET
                  rating = EXCLUDED.rating,
                  comment = EXCLUDED.comment,
                  updated_at = now()
                RETURNING id, rating, comment, created_at, updated_at
                """,
                (
                    tenant_id,
                    user_id,
                    conversation_id,
                    message_position,
                    rating,
                    (comment or "").strip()[:500] or None,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise RuntimeError("feedback upsert returned no row")
    return {
        "id": str(row[0]),
        "rating": int(row[1]),
        "comment": row[2],
        "created_at": row[3].isoformat() if row[3] else None,
        "updated_at": row[4].isoformat() if row[4] else None,
    }


def list_feedback_for_conversation(
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> list[dict[str, Any]]:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_position, rating, comment, updated_at
                FROM chat_message_feedback
                WHERE user_id = %s AND conversation_id = %s
                ORDER BY message_position ASC
                """,
                (user_id, conversation_id),
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "message_position": int(r[0]),
                "rating": int(r[1]),
                "comment": r[2],
                "updated_at": r[3].isoformat() if r[3] else None,
            }
        )
    return out


def list_feedback_admin(*, tenant_id: int, limit: int = 100) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 500))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT f.id, f.user_id, f.conversation_id, f.message_position,
                       f.rating, f.comment, f.created_at, f.updated_at
                FROM chat_message_feedback f
                WHERE f.tenant_id = %s
                ORDER BY f.updated_at DESC
                LIMIT %s
                """,
                (tenant_id, lim),
            )
            rows = cur.fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": str(r[0]),
                "user_id": str(r[1]),
                "conversation_id": str(r[2]),
                "message_position": int(r[3]),
                "rating": int(r[4]),
                "comment": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
                "updated_at": r[7].isoformat() if r[7] else None,
            }
        )
    return out
