"""Encrypted ephemeral storage for chat secret ingress (ADR 0006)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from apps.backend.infrastructure.platform import config
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


def vault_available() -> bool:
    return bool(config.CHAT_SECRET_INGRESS_ENABLED and config.CHAT_SECRET_VAULT_FERNET_KEY)


def _fernet() -> Fernet | None:
    raw = (config.CHAT_SECRET_VAULT_FERNET_KEY or "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode("ascii"))
    except Exception as e:
        logger.warning("CHAT_SECRET_VAULT_FERNET_KEY invalid: %s", e)
        return None


def vault_store(*, tenant_id: int, user_id: uuid.UUID, slot: str, plaintext: str) -> uuid.UUID | None:
    """Insert ciphertext row; return new id or None if vault disabled / misconfigured."""
    if not vault_available():
        return None
    f = _fernet()
    if f is None:
        return None
    slot_s = (slot or "").strip()
    if not slot_s or len(plaintext) > 16384:
        return None
    vid = uuid.uuid4()
    ct = f.encrypt(plaintext.encode("utf-8"))
    ttl = max(5, int(config.CHAT_SECRET_VAULT_TTL_MINUTES or 30))
    exp = datetime.now(tz=UTC) + timedelta(minutes=ttl)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_secret_vault
                  (id, tenant_id, user_id, slot, ciphertext, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (vid, int(tenant_id), user_id, slot_s, ct, exp),
            )
        conn.commit()
    return vid


def vault_get_plaintext(
    token_id: uuid.UUID,
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    consume: bool = False,
) -> str | None:
    """Decrypt if row exists, matches identity, not expired, and optionally mark consumed."""
    if not vault_available():
        return None
    f = _fernet()
    if f is None:
        return None
    now = datetime.now(tz=UTC)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ciphertext, expires_at, consumed_at, tenant_id, user_id
                FROM chat_secret_vault WHERE id = %s
                """,
                (token_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            ct, exp, consumed, row_tid, row_uid = row[0], row[1], row[2], int(row[3]), row[4]
            if row_uid != user_id or row_tid != int(tenant_id):
                return None
            if consumed is not None:
                return None
            if exp is not None and getattr(exp, "tzinfo", None) is None:
                exp = exp.replace(tzinfo=UTC)
            if exp is not None and now > exp:
                return None
            try:
                plain = f.decrypt(bytes(ct)).decode("utf-8")
            except InvalidToken:
                logger.warning("chat_secret_vault: decrypt failed for id=%s", token_id)
                return None
            if consume:
                cur.execute(
                    "UPDATE chat_secret_vault SET consumed_at = %s WHERE id = %s",
                    (now, token_id),
                )
        conn.commit()
    return plain


def vault_consume_tokens_in_string(s: str, *, tenant_id: int, user_id: uuid.UUID) -> None:
    """Mark vault rows consumed for every placeholder id found in ``s`` (no decrypt)."""
    import re

    if not vault_available() or not s:
        return
    now = datetime.now(tz=UTC)
    for m in re.finditer(
        r"\[\[agentlayer:secret:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]",
        s,
    ):
        try:
            uid = uuid.UUID(m.group(1))
        except ValueError:
            continue
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_secret_vault SET consumed_at = %s
                    WHERE id = %s AND user_id = %s AND tenant_id = %s
                      AND consumed_at IS NULL AND expires_at > %s
                    """,
                    (now, uid, user_id, int(tenant_id), now),
                )
            conn.commit()
