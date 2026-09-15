"""API key management for Agent Layer.

Opaque bearer secrets prefixed with ``al_``. Keys are stored as fixed-length
SHA-256 digests for indexed DB lookup (not bcrypt — API keys are high-entropy and
must survive indexed equality lookups). This module deliberately imports nothing
from ``auth`` so it can be used without a dependency cycle.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from apps.backend.infrastructure.db import db

API_KEY_PREFIX = "al_"


def hash_api_key(token: str) -> str:
    """Fixed-length digest for indexed DB lookup (not bcrypt — API keys are high-entropy)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Opaque bearer secret. The prefix makes it recognisable in logs and secret scanners."""
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def create_api_key(
    user_id: uuid.UUID,
    name: str,
    expires_at: Optional[datetime] = None,
) -> tuple[str, dict[str, Any]]:
    """Mint a key. Returns (secret, metadata) — the secret is not recoverable afterwards."""
    token = generate_api_key()
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_keys (user_id, key_hash, name, expires_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, created_at, last_used_at, expires_at
                """,
                (user_id, hash_api_key(token), name, expires_at),
            )
            row = cur.fetchone()
        conn.commit()
    meta = {
        "id": str(row[0]),
        "name": row[1],
        "created_at": row[2],
        "last_used_at": row[3],
        "expires_at": row[4],
    }
    return token, meta


def list_api_keys(user_id: uuid.UUID) -> list[dict[str, Any]]:
    """Metadata only — the secret is never stored and cannot be listed."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, created_at, last_used_at, expires_at
                FROM api_keys
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "created_at": r[2],
            "last_used_at": r[3],
            "expires_at": r[4],
            "expired": bool(r[4] and r[4] <= datetime.now(timezone.utc)),
        }
        for r in rows
    ]


def revoke_api_key(user_id: uuid.UUID, key_id: uuid.UUID) -> bool:
    """Scoped by user_id so one user cannot revoke another's key."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM api_keys WHERE id = %s AND user_id = %s",
                (key_id, user_id),
            )
            deleted = cur.rowcount
        conn.commit()
    return deleted > 0
