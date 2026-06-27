"""Persistence helpers for benchmark autotune sessions."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.rows import dict_row

from apps.backend.infrastructure.db import db


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def create_session(
    *,
    tenant_id: int,
    user_id: uuid.UUID | None,
    mode: str,
    catalog_owned_by: str,
    model: str,
    profiles: list[dict[str, Any]],
    plan: dict[str, Any],
) -> dict[str, Any]:
    sid = uuid.uuid4()
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO benchmark_tuning_sessions (
                  id, tenant_id, user_id, status, mode, catalog_owned_by, model,
                  profiles_json, plan_json
                ) VALUES (%s, %s, %s, 'queued', %s, %s, %s, %s::jsonb, %s::jsonb)
                RETURNING *
                """,
                (
                    sid,
                    tenant_id,
                    user_id,
                    mode,
                    catalog_owned_by,
                    model,
                    json.dumps(profiles),
                    json.dumps(plan),
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()
    return _serialize(row)


def get_session(session_id: uuid.UUID, *, tenant_id: int | None = None) -> dict[str, Any] | None:
    where = ["id = %s"]
    params: list[Any] = [session_id]
    if tenant_id is not None:
        where.append("tenant_id = %s")
        params.append(tenant_id)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"SELECT * FROM benchmark_tuning_sessions WHERE {' AND '.join(where)}",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def list_sessions(*, tenant_id: int, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(100, int(limit)))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT *
                FROM benchmark_tuning_sessions
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, lim),
            )
            rows = [dict(r) for r in cur.fetchall()]
        conn.commit()
    return [_serialize(r) for r in rows]


def update_session(session_id: uuid.UUID, **fields: Any) -> dict[str, Any] | None:
    allowed = {
        "status",
        "attempts_json",
        "best_run_id",
        "best_score",
        "best_patches_json",
        "promoted_at",
        "error_text",
        "finished_at",
    }
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = []
    for key, val in fields.items():
        if key not in allowed:
            continue
        if key in ("attempts_json", "best_patches_json") and val is not None:
            sets.append(f"{key} = %s::jsonb")
            params.append(json.dumps(val))
        else:
            sets.append(f"{key} = %s")
            params.append(val)
    params.append(session_id)
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"UPDATE benchmark_tuning_sessions SET {', '.join(sets)} WHERE id = %s RETURNING *",
                params,
            )
            row = cur.fetchone()
        conn.commit()
    return _serialize(dict(row)) if row else None


def append_attempt(session_id: uuid.UUID, attempt: dict[str, Any]) -> dict[str, Any] | None:
    row = get_session(session_id)
    if not row:
        return None
    attempts = row.get("attempts_json")
    if not isinstance(attempts, list):
        attempts = []
    attempts.append(attempt)
    return update_session(session_id, attempts_json=attempts)
