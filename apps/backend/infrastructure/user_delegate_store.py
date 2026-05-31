"""Persisted global User Delegate (Stellvertreter) config."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.domain.delegate_config_schema import normalize_delegate_config, normalize_delegate_notes
from apps.backend.infrastructure.db import db


def _iso(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.astimezone(UTC).isoformat()
    return str(dt)


def get_user_delegate(*, user_id: uuid.UUID) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT user_id, tenant_id, config, notes, updated_at
                FROM user_delegate
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()


def upsert_user_delegate(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    config: dict[str, Any],
    notes: str = "",
) -> dict[str, Any]:
    cfg = normalize_delegate_config(config, scope="user")
    notes_s = normalize_delegate_notes(notes)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO user_delegate (user_id, tenant_id, config, notes, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET
                  config = EXCLUDED.config,
                  notes = EXCLUDED.notes,
                  updated_at = now()
                RETURNING user_id, tenant_id, config, notes, updated_at
                """,
                (user_id, tenant_id, Json(cfg), notes_s),
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        raise RuntimeError("user_delegate upsert returned no row")
    out = dict(row)
    out["updated_at"] = _iso(out.get("updated_at"))
    return out
