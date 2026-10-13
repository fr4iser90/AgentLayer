"""Load/save per-conversation context-inject digests (on-change injects)."""

from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Json

from apps.backend.infrastructure.db import db


def get_inject_digests(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> dict[str, dict[str, str]]:
    """Return ``{ agent_id: { kind: digest } }``."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT context_inject_digests
                FROM chat_conversations
                WHERE id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return {}
    raw = row[0]
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, str]] = {}
    for agent_id, kinds in raw.items():
        if not isinstance(agent_id, str) or not isinstance(kinds, dict):
            continue
        cleaned: dict[str, str] = {}
        for kind, digest in kinds.items():
            if isinstance(kind, str) and isinstance(digest, str) and digest.strip():
                cleaned[kind] = digest.strip()
        if cleaned:
            out[agent_id.strip().lower() or "default"] = cleaned
    return out


def set_inject_digests(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    digests: dict[str, dict[str, str]],
) -> None:
    payload: dict[str, Any] = {}
    for agent_id, kinds in digests.items():
        if not isinstance(agent_id, str) or not isinstance(kinds, dict):
            continue
        cleaned = {
            str(k): str(v)
            for k, v in kinds.items()
            if str(k).strip() and str(v).strip()
        }
        if cleaned:
            payload[agent_id.strip().lower() or "default"] = cleaned
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_conversations
                SET context_inject_digests = %s, updated_at = now()
                WHERE id = %s AND user_id = %s
                """,
                (Json(payload), conversation_id, user_id),
            )
        conn.commit()
