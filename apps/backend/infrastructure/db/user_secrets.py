from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.db.db import pool

def user_secret_upsert(user_id: uuid.UUID, service_key: str, plaintext: str) -> None:
    from apps.backend.infrastructure.identity.crypto_secrets import encrypt_secret

    ct = encrypt_secret(plaintext)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_secrets (user_id, service_key, ciphertext)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, service_key) DO UPDATE SET
                  ciphertext = EXCLUDED.ciphertext,
                  updated_at = now()
                """,
                (user_id, service_key, ct),
            )
        conn.commit()


def user_secret_get_plaintext(user_id: uuid.UUID, service_key: str) -> str | None:
    """Server-side only — never return this to LLM tool JSON."""
    from apps.backend.infrastructure.identity.crypto_secrets import decrypt_secret

    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ciphertext FROM user_secrets
                WHERE user_id = %s AND service_key = %s
                """,
                (user_id, service_key),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return decrypt_secret(bytes(row[0]))


def user_secret_delete(user_id: uuid.UUID, service_key: str) -> bool:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_secrets
                WHERE user_id = %s AND service_key = %s
                """,
                (user_id, service_key),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def user_secret_list_service_keys(user_id: uuid.UUID) -> list[str]:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT service_key FROM user_secrets
                WHERE user_id = %s
                ORDER BY service_key
                """,
                (user_id,),
            )
            rows = cur.fetchall()
        conn.commit()
    return [str(r[0]) for r in rows]


def secret_upload_otp_create(user_id: uuid.UUID, ttl_seconds: int = 600) -> str:
    """Insert a one-time registration token; return plaintext OTP (show once)."""
    raw = secrets.token_urlsafe(18)
    otp_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO secret_upload_otps (user_id, otp_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (user_id, otp_hash, expires),
            )
        conn.commit()
    return raw


def user_secret_register_with_otp(
    otp_raw: str, service_key: str, plaintext: str
) -> None:
    """Validate OTP (single-use), then upsert encrypted secret for bound user."""
    from apps.backend.infrastructure.identity.crypto_secrets import encrypt_secret

    otp_raw = (otp_raw or "").strip()
    if not otp_raw:
        raise ValueError("otp is required")
    otp_hash = hashlib.sha256(otp_raw.encode("utf-8")).hexdigest()
    ct = encrypt_secret(plaintext)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, used_at, expires_at
                FROM secret_upload_otps
                WHERE otp_hash = %s
                FOR UPDATE
                """,
                (otp_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    "unknown otp — check copy/paste (no spaces/line breaks), or mint a new one with register_secrets"
                )
            uid = row[0]
            if not isinstance(uid, uuid.UUID):
                uid = uuid.UUID(str(uid))
            used_at = row[1]
            expires_at = row[2]
            if used_at is not None:
                raise ValueError(
                    "otp already used (single-use) — call register_secrets again for a new curl_bash"
                )
            now_utc = datetime.now(UTC)
            if expires_at is not None:
                exp = expires_at
                if getattr(exp, "tzinfo", None) is None:
                    exp = exp.replace(tzinfo=UTC)
                if exp <= now_utc:
                    raise ValueError(
                        "otp expired — default validity 10 min; call register_secrets again"
                    )
            cur.execute(
                """
                UPDATE secret_upload_otps SET used_at = now()
                WHERE otp_hash = %s AND used_at IS NULL
                """,
                (otp_hash,),
            )
            cur.execute(
                """
                INSERT INTO user_secrets (user_id, service_key, ciphertext)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, service_key) DO UPDATE SET
                  ciphertext = EXCLUDED.ciphertext,
                  updated_at = now()
                """,
                (uid, service_key, ct),
            )
        conn.commit()


