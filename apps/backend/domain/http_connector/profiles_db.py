"""Persist reusable HTTP connector profiles per user."""

from __future__ import annotations

import re
import uuid
from typing import Any

from psycopg.types.json import Json

from apps.backend.domain.http_connector.ssrf import validate_outbound_url
from apps.backend.infrastructure.db import db

_PROFILE_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def normalize_profile_id(raw: str) -> str | None:
    s = (raw or "").strip().lower()
    if not s or not _PROFILE_ID_RE.match(s):
        return None
    return s


def connector_profile_upsert(
    user_id: uuid.UUID,
    profile_id: str,
    *,
    label: str | None,
    base_url: str,
    auth: dict[str, Any],
    default_headers: dict[str, Any],
    endpoints: dict[str, Any],
) -> dict[str, Any] | None:
    pid = normalize_profile_id(profile_id)
    if pid is None:
        return None
    base = (base_url or "").strip()
    if not base:
        return None
    if not base.startswith("http://") and not base.startswith("https://"):
        base = "https://" + base.lstrip("/")
    ok, _why = validate_outbound_url(base)
    if not ok:
        return None

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_connector_profiles (
                  user_id, profile_id, label, base_url, auth, default_headers, endpoints
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id, profile_id) DO UPDATE SET
                  label = EXCLUDED.label,
                  base_url = EXCLUDED.base_url,
                  auth = EXCLUDED.auth,
                  default_headers = EXCLUDED.default_headers,
                  endpoints = EXCLUDED.endpoints,
                  updated_at = now()
                RETURNING profile_id, label, base_url, auth, default_headers, endpoints,
                          created_at, updated_at
                """,
                (
                    user_id,
                    pid,
                    (label or "").strip() or pid,
                    base,
                    Json(auth if isinstance(auth, dict) else {}),
                    Json(default_headers if isinstance(default_headers, dict) else {}),
                    Json(endpoints if isinstance(endpoints, dict) else {}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "profile_id": row[0],
        "label": row[1],
        "base_url": row[2],
        "auth": row[3] if isinstance(row[3], dict) else {},
        "default_headers": row[4] if isinstance(row[4], dict) else {},
        "endpoints": row[5] if isinstance(row[5], dict) else {},
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def connector_profile_get(user_id: uuid.UUID, profile_id: str) -> dict[str, Any] | None:
    pid = normalize_profile_id(profile_id)
    if pid is None:
        return None
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT profile_id, label, base_url, auth, default_headers, endpoints,
                       created_at, updated_at
                FROM user_connector_profiles
                WHERE user_id = %s AND profile_id = %s
                """,
                (user_id, pid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "profile_id": row[0],
        "label": row[1],
        "base_url": row[2],
        "auth": row[3] if isinstance(row[3], dict) else {},
        "default_headers": row[4] if isinstance(row[4], dict) else {},
        "endpoints": row[5] if isinstance(row[5], dict) else {},
        "created_at": row[6].isoformat() if row[6] else None,
        "updated_at": row[7].isoformat() if row[7] else None,
    }


def connector_profile_list(user_id: uuid.UUID, limit: int = 50) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 100))
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT profile_id, label, base_url, endpoints
                FROM user_connector_profiles
                WHERE user_id = %s
                ORDER BY profile_id
                LIMIT %s
                """,
                (user_id, lim),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for row in rows:
        eps = row[3] if isinstance(row[3], dict) else {}
        out.append(
            {
                "profile_id": row[0],
                "label": row[1],
                "base_url": row[2],
                "endpoint_names": sorted(eps.keys()) if eps else [],
            }
        )
    return out


def connector_profile_delete(user_id: uuid.UUID, profile_id: str) -> bool:
    pid = normalize_profile_id(profile_id)
    if pid is None:
        return False
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_connector_profiles
                WHERE user_id = %s AND profile_id = %s
                """,
                (user_id, pid),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0
