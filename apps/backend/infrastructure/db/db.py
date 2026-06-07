"""PostgreSQL pool and persistence helpers. Schema changes: Alembic (see entrypoint)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("database pool not initialized")
    return _pool


def init_pool() -> None:
    global _pool
    if not config.DATABASE_URL:
        raise RuntimeError(
            "PostgreSQL connection missing: DATABASE_URL is empty and could not be built from "
            "POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB (and PGHOST defaulting to postgres). "
            "Fix: set DATABASE_URL in docker/.env (see .env.example), or pass the same POSTGRES_* "
            "variables into the agent-layer container as for the postgres service, then restart."
        )
    if _pool is not None:
        return
    _pool = ConnectionPool(
        conninfo=config.DATABASE_URL,
        min_size=1,
        max_size=10,
        kwargs={"autocommit": False},
    )
    logger.info("PostgreSQL pool ready")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def tenants_list() -> list[dict[str, Any]]:
    """All rows from ``tenants`` (for admin UI: ids used in tool allowlists and ``users.tenant_id``)."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, name, created_at
                FROM tenants
                ORDER BY id ASC
                """
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        ca = d.get("created_at")
        if ca is not None and hasattr(ca, "isoformat"):
            d["created_at"] = ca.isoformat()
        out.append(d)
    return out


def tenant_exists(tenant_id: int) -> bool:
    if tenant_id < 1:
        return False
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM tenants WHERE id = %s", (tenant_id,))
            ok = cur.fetchone() is not None
        conn.commit()
    return ok


def tenant_insert(name: str) -> dict[str, Any]:
    """Insert a tenant row; ``name`` trim, fallback label if empty."""
    label = (name or "").strip() or "tenant"
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "INSERT INTO tenants (name) VALUES (%s) RETURNING id, name, created_at",
                (label,),
            )
            row = cur.fetchone()
        conn.commit()
    d = dict(row)
    ca = d.get("created_at")
    if ca is not None and hasattr(ca, "isoformat"):
        d["created_at"] = ca.isoformat()
    return d


def user_external_sub(user_id: uuid.UUID) -> str | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT external_sub FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return str(row[0]) if row[0] is not None else None


def user_tenant_id(user_id: uuid.UUID) -> int:
    """``users.tenant_id`` for FK-scoped data and tool policy (defaults to ``1``)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT tenant_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return 1
    try:
        t = int(row[0])
    except (TypeError, ValueError):
        return 1
    return t if t >= 1 else 1


def user_first_admin_id() -> uuid.UUID | None:
    """Oldest user with ``role = 'admin'`` (for bootstrap jobs that need an owning user id)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE role = 'admin' ORDER BY created_at ASC LIMIT 1"
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


_DISCORD_NUMERIC_USER_ID = re.compile(r"^[0-9]{15,22}$")


def discord_user_id_normalize(raw: str) -> str:
    s = (raw or "").strip()
    if not _DISCORD_NUMERIC_USER_ID.match(s):
        raise ValueError("Discord user id must be a numeric id (15–22 digits), from Copy User ID in Discord.")
    return s


def user_discord_user_id_get(user_id: uuid.UUID) -> str | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT discord_user_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    out = str(row[0]).strip()
    return out or None


def user_discord_user_id_set(user_id: uuid.UUID, tenant_id: int, raw: str) -> str | None:
    """
    Set or clear ``users.discord_user_id``. Empty / whitespace ``raw`` clears the link.
    Returns the stored value (or None if cleared).
    """
    stripped = (raw or "").strip()
    new_val: str | None = None if not stripped else discord_user_id_normalize(stripped)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users SET discord_user_id = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (new_val, user_id, tenant_id),
            )
            if (cur.rowcount or 0) < 1:
                raise ValueError("user not found")
        conn.commit()
    return new_val


def user_id_for_discord_user_id(tenant_id: int, discord_user_id: str) -> uuid.UUID | None:
    """Resolve AgentLayer user id from Discord numeric user id within a tenant (for bots with DB access)."""
    sid = discord_user_id_normalize(discord_user_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND discord_user_id = %s",
                (tenant_id, sid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def user_id_tenant_for_discord_global(discord_user_id: str) -> tuple[uuid.UUID, int] | None:
    """
    Resolve (user_id, tenant_id) from a linked Discord numeric user id (any tenant).
    Returns None if unlinked, invalid id, or more than one row (ambiguous).
    """
    try:
        sid = discord_user_id_normalize(discord_user_id)
    except ValueError:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tenant_id FROM users WHERE discord_user_id = %s",
                (sid,),
            )
            rows = cur.fetchall()
        conn.commit()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "multiple users share the same discord_user_id; Discord bridge refuses ambiguous resolution"
        )
        return None
    uid, tid = rows[0]
    user_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    try:
        tenant_id = int(tid) if tid is not None else 1
    except (TypeError, ValueError):
        tenant_id = 1
    return user_uuid, tenant_id if tenant_id >= 1 else 1


_TELEGRAM_NUMERIC_USER_ID = re.compile(r"^[0-9]{5,20}$")


def telegram_user_id_normalize(raw: str) -> str:
    s = (raw or "").strip()
    if not _TELEGRAM_NUMERIC_USER_ID.match(s):
        raise ValueError(
            "Telegram user id must be numeric (5–20 digits). Use @userinfobot or Telegram settings to get your id."
        )
    return s


def user_telegram_user_id_get(user_id: uuid.UUID) -> str | None:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT telegram_user_id FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return None
    out = str(row[0]).strip()
    return out or None


def user_telegram_user_id_set(user_id: uuid.UUID, tenant_id: int, raw: str) -> str | None:
    """
    Set or clear ``users.telegram_user_id``. Empty / whitespace ``raw`` clears the link.
    Returns the stored value (or None if cleared).
    """
    stripped = (raw or "").strip()
    new_val: str | None = None if not stripped else telegram_user_id_normalize(stripped)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users SET telegram_user_id = %s
                WHERE id = %s AND tenant_id = %s
                """,
                (new_val, user_id, tenant_id),
            )
            if (cur.rowcount or 0) < 1:
                raise ValueError("user not found")
        conn.commit()
    return new_val


def user_id_for_telegram_user_id(tenant_id: int, telegram_user_id: str) -> uuid.UUID | None:
    """Resolve AgentLayer user id from Telegram user id within a tenant (for bots with DB access)."""
    sid = telegram_user_id_normalize(telegram_user_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM users WHERE tenant_id = %s AND telegram_user_id = %s",
                (tenant_id, sid),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


def user_id_tenant_for_telegram_global(telegram_user_id: str) -> tuple[uuid.UUID, int] | None:
    """
    Resolve (user_id, tenant_id) from a linked Telegram user id (any tenant).
    Returns None if unlinked, invalid id, or more than one row (ambiguous).
    """
    try:
        sid = telegram_user_id_normalize(telegram_user_id)
    except ValueError:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, tenant_id FROM users WHERE telegram_user_id = %s",
                (sid,),
            )
            rows = cur.fetchall()
        conn.commit()
    if not rows:
        return None
    if len(rows) > 1:
        logger.warning(
            "multiple users share the same telegram_user_id; Telegram bridge refuses ambiguous resolution"
        )
        return None
    uid, tid = rows[0]
    user_uuid = uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))
    try:
        tenant_id = int(tid) if tid is not None else 1
    except (TypeError, ValueError):
        tenant_id = 1
    return user_uuid, tenant_id if tenant_id >= 1 else 1


def user_role(user_id: uuid.UUID | None) -> str:
    """Return ``users.role`` (``user`` or ``admin``) for tool access checks."""
    if user_id is None:
        return "user"
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return "user"
    r = str(row[0]).strip().lower()
    return r if r in ("user", "admin") else "user"


def scheduler_outbound_count_today_utc(user_id: uuid.UUID) -> int:
    """Rows in ``scheduler_outbound_daily`` for today's UTC date."""
    day = datetime.now(UTC).date()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT outbound_count FROM scheduler_outbound_daily WHERE user_id = %s AND day_utc = %s",
                (user_id, day),
            )
            row = cur.fetchone()
        conn.commit()
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def scheduler_outbound_increment_utc(user_id: uuid.UUID) -> int:
    """Upsert +1 for today UTC; returns new count."""
    day = datetime.now(UTC).date()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduler_outbound_daily (user_id, day_utc, outbound_count)
                VALUES (%s, %s, 1)
                ON CONFLICT (user_id, day_utc) DO UPDATE SET
                  outbound_count = scheduler_outbound_daily.outbound_count + 1
                RETURNING outbound_count
                """,
                (user_id, day),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return 1
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 1


def _require_user_uuid() -> tuple[int, uuid.UUID]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        raise ValueError(
            "no user identity in this context (chat/tool requests need user/tenant headers)"
        )
    return tenant_id, user_id


def todo_create(title: str) -> int:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO todos (title, tenant_id, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (title, tenant_id, user_id),
            )
            row = cur.fetchone()
            tid = int(row[0])
        conn.commit()
        return tid


def todo_list(limit: int = 100) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, title, status, created_at, updated_at
                FROM todos
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def todo_set_status(todo_id: int, status: str) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE todos
                SET status = %s, updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s
                """,
                (status, todo_id, tenant_id, user_id),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def log_tool_invocation(
    tool_name: str,
    args: dict[str, Any],
    result_text: str,
    ok: bool,
    *,
    agent_run_id: uuid.UUID | str | None = None,
) -> None:
    excerpt = (result_text or "")[:4000]
    tenant_id, user_id = get_identity()
    if user_id is None:
        return
    args_for_db: Any = args
    if isinstance(args, dict):
        redact = config.tool_log_redact_keys()
        if redact:
            args_for_db = {}
            for k, v in args.items():
                if k in redact and isinstance(v, str):
                    if len(v) > 200:
                        args_for_db[k] = f"<omitted {len(v)} chars>"
                    else:
                        args_for_db[k] = "<redacted>"
                else:
                    args_for_db[k] = v
    try:
        with pool().connection() as conn:
            with conn.cursor() as cur:
                run_uuid: uuid.UUID | None = None
                if agent_run_id is not None:
                    try:
                        run_uuid = (
                            agent_run_id
                            if isinstance(agent_run_id, uuid.UUID)
                            else uuid.UUID(str(agent_run_id).strip())
                        )
                    except (ValueError, TypeError):
                        run_uuid = None
                if run_uuid is not None and tenant_id is not None:
                    from apps.backend.infrastructure import agent_runs_store

                    if not agent_runs_store.run_exists(
                        run_id=run_uuid, tenant_id=int(tenant_id)
                    ):
                        logger.warning(
                            "tool_invocation %s: agent_run_id %s not in agent_runs; logging without run link",
                            tool_name,
                            run_uuid,
                        )
                        run_uuid = None
                cur.execute(
                    """
                    INSERT INTO tool_invocations
                      (tool_name, args_json, result_excerpt, ok, tenant_id, user_id, agent_run_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (tool_name, Json(args_for_db), excerpt, ok, tenant_id, user_id, run_uuid),
                )
            conn.commit()
    except psycopg.Error:
        logger.exception("failed to log tool_invocation for %s", tool_name)


def recent_tool_invocations(limit: int = 50) -> list[dict[str, Any]]:
    tenant_id, user_id = get_identity()
    if user_id is None:
        return []
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, tool_name, args_json, result_excerpt, ok, created_at,
                       tenant_id, user_id
                FROM tool_invocations
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY id DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def user_secret_upsert(user_id: uuid.UUID, service_key: str, plaintext: str) -> None:
    from apps.backend.infrastructure.crypto_secrets import encrypt_secret

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
    from apps.backend.infrastructure.crypto_secrets import decrypt_secret

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
    from apps.backend.infrastructure.crypto_secrets import encrypt_secret

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


def kb_note_append(title: str, body: str) -> int:
    tenant_id, user_id = _require_user_uuid()
    title = (title or "").strip()
    body = (body or "").strip()
    if not body:
        raise ValueError("body is required")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_kb_notes (title, body, tenant_id, user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (title, body, tenant_id, user_id),
            )
            row = cur.fetchone()
            nid = int(row[0])
        conn.commit()
    return nid


def _ilike_contains(s: str) -> str:
    esc = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def kb_note_search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    q = (query or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit or 20), 50))
    pat = _ilike_contains(q)
    sql_full = """
                SELECT id, title, left(body, 500) AS body_excerpt, created_at
                FROM user_kb_notes
                WHERE tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                  AND (
                    title ILIKE %s ESCAPE '\\'
                    OR body ILIKE %s ESCAPE '\\'
                    OR search_tsv @@ websearch_to_tsquery('simple', %s)
                  )
                ORDER BY created_at DESC
                LIMIT %s
                """
    sql_ilike = """
                SELECT id, title, left(body, 500) AS body_excerpt, created_at
                FROM user_kb_notes
                WHERE tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                  AND (
                    title ILIKE %s ESCAPE '\\'
                    OR body ILIKE %s ESCAPE '\\'
                  )
                ORDER BY created_at DESC
                LIMIT %s
                """
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                cur.execute(
                    sql_full,
                    (tenant_id, user_id, user_id, pat, pat, q, limit),
                )
            except psycopg.Error:
                logger.debug(
                    "kb_note_search fts fallback for query %r", q[:80], exc_info=True
                )
                conn.rollback()
                cur.execute(
                    sql_ilike,
                    (tenant_id, user_id, user_id, pat, pat, limit),
                )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "title": r["title"],
                "body_excerpt": r["body_excerpt"],
                "created_at": (
                    r["created_at"].isoformat() if r.get("created_at") else None
                ),
            }
        )
    return out


def kb_note_get(note_id: int, max_body_chars: int = 12000) -> dict[str, Any] | None:
    tenant_id, user_id = _require_user_uuid()
    max_body_chars = max(500, min(int(max_body_chars or 12000), 100_000))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, title, body, created_at, updated_at, user_id AS owner_user_id
                FROM user_kb_notes
                WHERE id = %s AND tenant_id = %s
                  AND (
                    user_id = %s
                    OR id IN (
                      SELECT note_id FROM user_kb_note_shares
                      WHERE grantee_user_id = %s
                    )
                  )
                """,
                (note_id, tenant_id, user_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    body = str(row["body"] or "")
    if len(body) > max_body_chars:
        body = body[:max_body_chars] + "\n… (truncated)"
    owner_uid = row.get("owner_user_id")
    return {
        "id": row["id"],
        "title": row["title"],
        "body": body,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "is_owner": owner_uid == user_id,
        "owner_user_id": str(owner_uid) if owner_uid is not None else None,
    }


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in vec) + "]"


def memory_fact_upsert(
    *,
    key: str,
    value_json: Any,
    dashboard_id: uuid.UUID | None = None,
    confidence: float | None = None,
    source: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Upsert one structured memory fact for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    k = (key or "").strip()
    if not k:
        raise ValueError("key is required")
    conf = float(confidence) if confidence is not None else 1.0
    conf = max(0.0, min(conf, 1.0))
    src = (source or "user").strip() or "user"
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if dashboard_id is None:
                cur.execute(
                    """
                    INSERT INTO user_memory_facts
                      (tenant_id, user_id, dashboard_id, key, value_json, confidence, source, expires_at, deleted_at)
                    VALUES (%s, %s, NULL, %s, %s::jsonb, %s, %s, %s, NULL)
                    ON CONFLICT (tenant_id, user_id, key)
                      WHERE dashboard_id IS NULL AND deleted_at IS NULL
                    DO UPDATE SET
                      value_json = EXCLUDED.value_json,
                      confidence = EXCLUDED.confidence,
                      source = EXCLUDED.source,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = now(),
                      deleted_at = NULL
                    RETURNING id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                    """,
                    (tenant_id, user_id, k, Json(value_json), conf, src, expires_at),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO user_memory_facts
                      (tenant_id, user_id, dashboard_id, key, value_json, confidence, source, expires_at, deleted_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL)
                    ON CONFLICT (tenant_id, user_id, dashboard_id, key)
                      WHERE dashboard_id IS NOT NULL AND deleted_at IS NULL
                    DO UPDATE SET
                      value_json = EXCLUDED.value_json,
                      confidence = EXCLUDED.confidence,
                      source = EXCLUDED.source,
                      expires_at = EXCLUDED.expires_at,
                      updated_at = now(),
                      deleted_at = NULL
                    RETURNING id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                    """,
                    (tenant_id, user_id, dashboard_id, k, Json(value_json), conf, src, expires_at),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("upsert failed")
    return {
        "id": row["id"],
        "key": row["key"],
        "value_json": row["value_json"],
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else 1.0,
        "source": row["source"],
        "dashboard_id": str(row["dashboard_id"]) if row.get("dashboard_id") else None,
        "expires_at": row["expires_at"].isoformat() if row.get("expires_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def memory_fact_list(
    *,
    dashboard_id: uuid.UUID | None = None,
    prefix: str | None = None,
    limit: int = 50,
    include_expired: bool = False,
) -> list[dict[str, Any]]:
    """List active facts for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 50), 200))
    pre = (prefix or "").strip()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, key, value_json, confidence, source, dashboard_id, expires_at, updated_at
                FROM user_memory_facts
                WHERE tenant_id = %s
                  AND user_id = %s
                  AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                  AND deleted_at IS NULL
                  AND (%s OR expires_at IS NULL OR expires_at > now())
                  AND (%s = '' OR key ILIKE %s ESCAPE '\\')
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (
                    tenant_id,
                    user_id,
                    dashboard_id,
                    dashboard_id,
                    bool(include_expired),
                    pre,
                    _ilike_contains(pre) if pre else "",
                    limit,
                ),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "key": r["key"],
                "value_json": r["value_json"],
                "confidence": float(r.get("confidence") or 1.0),
                "source": r.get("source") or "",
                "dashboard_id": str(r["dashboard_id"]) if r.get("dashboard_id") else None,
                "expires_at": r["expires_at"].isoformat() if r.get("expires_at") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
            }
        )
    return out


def memory_fact_delete(*, key: str, dashboard_id: uuid.UUID | None = None) -> bool:
    """Soft-delete one fact by key for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    k = (key or "").strip()
    if not k:
        raise ValueError("key is required")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if dashboard_id is None:
                cur.execute(
                    """
                    UPDATE user_memory_facts
                    SET deleted_at = now(), updated_at = now()
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND dashboard_id IS NULL
                      AND key = %s
                      AND deleted_at IS NULL
                    """,
                    (tenant_id, user_id, k),
                )
            else:
                cur.execute(
                    """
                    UPDATE user_memory_facts
                    SET deleted_at = now(), updated_at = now()
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND dashboard_id = %s
                      AND key = %s
                      AND deleted_at IS NULL
                    """,
                    (tenant_id, user_id, dashboard_id, k),
                )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_note_insert(
    *,
    text: str,
    embedding: list[float],
    tags: list[str] | None = None,
    source: str | None = None,
    dashboard_id: uuid.UUID | None = None,
) -> int:
    """Insert one semantic memory note for the current identity (embedding provided by caller)."""
    tenant_id, user_id = _require_user_uuid()
    t = (text or "").strip()
    if not t:
        raise ValueError("text is required")
    tg = [str(x).strip() for x in (tags or []) if str(x).strip()]
    src = (source or "user").strip() or "user"
    ev = _vector_literal(embedding)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_memory_notes
                  (tenant_id, user_id, dashboard_id, text, tags, source, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                RETURNING id
                """,
                (tenant_id, user_id, dashboard_id, t, tg, src, ev),
            )
            nid = int(cur.fetchone()[0])
        conn.commit()
    return nid


def memory_note_soft_delete(note_id: int) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_memory_notes
                SET deleted_at = now(), updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (int(note_id), tenant_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_note_vector_search(
    *,
    query_embedding: list[float],
    dashboard_id: uuid.UUID | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Vector search over semantic memory notes for the current identity."""
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 10), 50))
    qv = _vector_literal(query_embedding)
    tg = [str(x).strip() for x in (tags or []) if str(x).strip()]
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if tg:
                cur.execute(
                    """
                    SELECT
                      id,
                      left(text, 4000) AS text,
                      tags,
                      source,
                      dashboard_id,
                      updated_at,
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_notes
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND deleted_at IS NULL
                      AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                      AND tags && %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, tg, qv, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT
                      id,
                      left(text, 4000) AS text,
                      tags,
                      source,
                      dashboard_id,
                      updated_at,
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_notes
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND deleted_at IS NULL
                      AND (%s::uuid IS NULL AND dashboard_id IS NULL OR dashboard_id = %s::uuid)
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, qv, limit),
                )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "text": r["text"],
                "tags": r.get("tags") or [],
                "source": r.get("source") or "",
                "dashboard_id": str(r["dashboard_id"]) if r.get("dashboard_id") else None,
                "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
                "distance": float(r.get("distance")) if r.get("distance") is not None else None,
            }
        )
    return out


def memory_graph_node_insert(
    *,
    dashboard_id: uuid.UUID | None,
    kind: str,
    label: str,
    summary: str,
    payload: dict[str, Any] | None,
    importance: float,
    embedding: list[float] | None = None,
    confidence: float | None = None,
    source: str | None = None,
    last_verified: datetime | None = None,
    subject_key: str | None = None,
    stability: str | None = None,
    priority: float | None = None,
) -> dict[str, Any]:
    """Insert one graph memory node for the current identity. Optional ``embedding`` (768-dim pgvector)."""
    tenant_id, user_id = _require_user_uuid()
    k = (kind or "event").strip() or "event"
    lab = (label or "").strip()
    if not lab:
        raise ValueError("label is required")
    summ = (summary or "").strip()
    pl = payload if isinstance(payload, dict) else {}
    imp = float(importance) if importance is not None else 1.0
    imp = max(0.0, min(imp, 10.0))
    conf = max(0.0, min(1.0, float(confidence) if confidence is not None else 1.0))
    src = (source or "user").strip() or "user"
    sk = (subject_key or "").strip() or None
    stab = (stability or "normal").strip().lower() or "normal"
    if stab not in ("volatile", "normal", "stable"):
        stab = "normal"
    prio = float(priority) if priority is not None else 0.0
    prio = max(-50.0, min(50.0, prio))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if embedding:
                ev = _vector_literal(embedding)
                cur.execute(
                    """
                    INSERT INTO user_memory_graph_nodes (
                      tenant_id, user_id, dashboard_id, kind, label, summary, payload, importance,
                      confidence, source, last_verified, subject_key, stability, priority,
                      embedding, deleted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s::vector, NULL)
                    RETURNING id, kind, label, summary, payload, importance, confidence, source,
                      last_verified, subject_key, stability, priority, dashboard_id, created_at, updated_at
                    """,
                    (
                        tenant_id,
                        user_id,
                        dashboard_id,
                        k,
                        lab,
                        summ,
                        Json(pl),
                        imp,
                        conf,
                        src,
                        last_verified,
                        sk,
                        stab,
                        prio,
                        ev,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO user_memory_graph_nodes (
                      tenant_id, user_id, dashboard_id, kind, label, summary, payload, importance,
                      confidence, source, last_verified, subject_key, stability, priority, deleted_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, NULL)
                    RETURNING id, kind, label, summary, payload, importance, confidence, source,
                      last_verified, subject_key, stability, priority, dashboard_id, created_at, updated_at
                    """,
                    (
                        tenant_id,
                        user_id,
                        dashboard_id,
                        k,
                        lab,
                        summ,
                        Json(pl),
                        imp,
                        conf,
                        src,
                        last_verified,
                        sk,
                        stab,
                        prio,
                    ),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("insert failed")
    return _memory_graph_node_row(row)


def memory_graph_edge_insert(
    *,
    src_node_id: int,
    dst_node_id: int,
    rel_type: str,
    weight: float,
) -> dict[str, Any]:
    """Insert an edge if both endpoints belong to the current user."""
    tenant_id, user_id = _require_user_uuid()
    if int(src_node_id) == int(dst_node_id):
        raise ValueError("src and dst must differ")
    rt = (rel_type or "related").strip() or "related"
    w = float(weight) if weight is not None else 1.0
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS c FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND id IN (%s, %s)
                """,
                (tenant_id, user_id, int(src_node_id), int(dst_node_id)),
            )
            cnt = cur.fetchone()
            if not cnt or int(cnt["c"]) != 2:
                raise ValueError("both nodes must exist and belong to this user")
            cur.execute(
                """
                INSERT INTO user_memory_graph_edges (
                  tenant_id, user_id, src_node_id, dst_node_id, rel_type, weight
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (src_node_id, dst_node_id, rel_type) DO UPDATE SET
                  weight = EXCLUDED.weight
                RETURNING id, src_node_id, dst_node_id, rel_type, weight, created_at
                """,
                (tenant_id, user_id, int(src_node_id), int(dst_node_id), rt, w),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise ValueError("edge insert failed")
    return {
        "id": int(row["id"]),
        "src_node_id": int(row["src_node_id"]),
        "dst_node_id": int(row["dst_node_id"]),
        "rel_type": row["rel_type"],
        "weight": float(row["weight"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
    }


def memory_graph_node_soft_delete(*, node_id: int) -> bool:
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE user_memory_graph_nodes
                SET deleted_at = now(), updated_at = now()
                WHERE id = %s AND tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                """,
                (int(node_id), tenant_id, user_id),
            )
            ok = cur.rowcount > 0
        conn.commit()
    return ok


def memory_graph_list_nodes(
    *,
    dashboard_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 100), 500))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, kind, label, left(summary, 4000) AS summary, payload, importance,
                  confidence, source, last_verified, subject_key, stability, priority,
                  dashboard_id, created_at, updated_at
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (tenant_id, user_id, dashboard_id, dashboard_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    return [_memory_graph_node_row(r) for r in rows]


def _memory_graph_node_row(row: Any) -> dict[str, Any]:
    lv = row.get("last_verified")
    cr = row.get("created_at")
    return {
        "id": int(row["id"]),
        "kind": row.get("kind") or "event",
        "label": row.get("label") or "",
        "summary": row.get("summary") or "",
        "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
        "importance": float(row.get("importance") or 1.0),
        "confidence": float(row.get("confidence") if row.get("confidence") is not None else 1.0),
        "source": str(row.get("source") or "user"),
        "last_verified": lv.isoformat() if lv else None,
        "subject_key": (str(row["subject_key"]).strip() if row.get("subject_key") is not None else None),
        "stability": str(row.get("stability") or "normal"),
        "priority": float(row.get("priority") if row.get("priority") is not None else 0.0),
        "dashboard_id": str(row["dashboard_id"]) if row.get("dashboard_id") else None,
        "created_at": cr.isoformat() if cr else "",
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else "",
    }


_GRAPH_NODE_SELECT = """
  id, kind, label, left(summary, 4000) AS summary, payload, importance,
  confidence, source, last_verified, subject_key, stability, priority,
  dashboard_id, created_at, updated_at
"""


def memory_graph_activate(
    *,
    dashboard_id: uuid.UUID | None,
    tokens: list[str],
    query_embedding: list[float] | None = None,
    vec_seed_limit: int = 8,
    keyword_seed_limit: int = 6,
    max_nodes: int = 14,
    max_hops: int = 2,
) -> list[dict[str, Any]]:
    """Hybrid activation: vector + keyword seeds, then multi-hop BFS along edges (cap ``max_nodes``)."""
    tenant_id, user_id = _require_user_uuid()
    clean: list[str] = []
    for t in tokens:
        s = str(t).strip().lower()[:80]
        if len(s) >= 2:
            clean.append(s)
    clean = clean[:24]

    qemb = query_embedding if query_embedding and len(query_embedding) >= 8 else None
    if not clean and not qemb:
        return []

    vec_seed_limit = max(1, min(int(vec_seed_limit), 50))
    keyword_seed_limit = max(1, min(int(keyword_seed_limit), 50))
    max_nodes = max(1, min(int(max_nodes), 50))
    max_hops = max(0, min(int(max_hops), 4))

    vec_rows: list[Any] = []
    seed_rows: list[Any] = []

    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if qemb:
                qv = _vector_literal(qemb)
                cur.execute(
                    f"""
                    SELECT {_GRAPH_NODE_SELECT.strip()},
                      (embedding <=> %s::vector) AS distance
                    FROM user_memory_graph_nodes
                    WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                      AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dashboard_id, dashboard_id, qv, vec_seed_limit),
                )
                vec_rows = cur.fetchall()

            if clean:
                or_parts: list[str] = []
                args: list[Any] = [tenant_id, user_id, dashboard_id, dashboard_id]
                for tok in clean:
                    pat = f"%{tok}%"
                    or_parts.append("(label ILIKE %s OR summary ILIKE %s)")
                    args.extend([pat, pat])
                or_sql = " OR ".join(or_parts)
                cur.execute(
                    f"""
                    SELECT {_GRAPH_NODE_SELECT.strip()}
                    FROM user_memory_graph_nodes
                    WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                      AND (dashboard_id IS NULL OR (%s::uuid IS NOT NULL AND dashboard_id = %s::uuid))
                      AND ({or_sql})
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (*args, keyword_seed_limit),
                )
                seed_rows = cur.fetchall()

        ordered_ids: list[int] = []
        for r in vec_rows:
            nid = int(r["id"])
            if nid not in ordered_ids:
                ordered_ids.append(nid)
        for r in seed_rows:
            nid = int(r["id"])
            if nid not in ordered_ids:
                ordered_ids.append(nid)

        seen: set[int] = set(ordered_ids)
        frontier = list(ordered_ids)
        for _hop in range(max_hops):
            if not frontier or len(seen) >= max_nodes:
                break
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT src_node_id, dst_node_id
                    FROM user_memory_graph_edges
                    WHERE tenant_id = %s AND user_id = %s
                      AND (src_node_id = ANY(%s::bigint[]) OR dst_node_id = ANY(%s::bigint[]))
                    """,
                    (tenant_id, user_id, frontier, frontier),
                )
                nxt: list[int] = []
                for row_e in cur.fetchall():
                    a, b = int(row_e[0]), int(row_e[1])
                    for u, v in ((a, b), (b, a)):
                        if u in frontier and v not in seen:
                            seen.add(v)
                            ordered_ids.append(v)
                            nxt.append(v)
                            if len(seen) >= max_nodes:
                                break
                    if len(seen) >= max_nodes:
                        break
            frontier = nxt

        ordered_ids = ordered_ids[:max_nodes]
        if not ordered_ids:
            conn.commit()
            return []

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {_GRAPH_NODE_SELECT.strip()}
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND id = ANY(%s::bigint[])
                """,
                (tenant_id, user_id, ordered_ids),
            )
            by_id = {int(r["id"]): r for r in cur.fetchall()}
        conn.commit()

    rank = {nid: i for i, nid in enumerate(ordered_ids)}
    out: list[dict[str, Any]] = []
    for nid in sorted(by_id.keys(), key=lambda x: rank.get(x, 999)):
        out.append(_memory_graph_node_row(by_id[nid]))
    return out


def memory_graph_stats() -> dict[str, Any]:
    """Counts for the current user (diagnostics / Admin)."""
    tenant_id, user_id = _require_user_uuid()
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  count(*) FILTER (WHERE deleted_at IS NULL)::bigint AS nodes_active,
                  count(*) FILTER (WHERE deleted_at IS NULL AND embedding IS NULL)::bigint AS nodes_no_embedding,
                  count(*) FILTER (WHERE deleted_at IS NULL AND subject_key IS NOT NULL)::bigint AS nodes_with_subject,
                  count(*) FILTER (WHERE deleted_at IS NULL AND kind = 'goal')::bigint AS nodes_goal
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s
                """,
                (tenant_id, user_id),
            )
            row = cur.fetchone()
            cur.execute(
                """
                SELECT COALESCE(subject_key, ''), count(*)::bigint AS c
                FROM user_memory_graph_nodes
                WHERE tenant_id = %s AND user_id = %s AND deleted_at IS NULL
                  AND subject_key IS NOT NULL
                GROUP BY subject_key
                HAVING count(*) > 1
                """,
                (tenant_id, user_id),
            )
            conf_groups = cur.fetchall()
        conn.commit()
    if not row:
        return {}
    conflict_keys = int(len(conf_groups or []))
    return {
        "nodes_active": int(row.get("nodes_active") or 0),
        "nodes_no_embedding": int(row.get("nodes_no_embedding") or 0),
        "nodes_with_subject": int(row.get("nodes_with_subject") or 0),
        "nodes_goal": int(row.get("nodes_goal") or 0),
        "subject_keys_with_conflicts": conflict_keys,
    }


def memory_graph_activation_log_insert(
    *,
    dashboard_id: uuid.UUID | None,
    node_ids: list[int],
    query_sha256: str | None,
    meta: dict[str, Any],
) -> int:
    """Append one activation record for the current user."""
    tenant_id, user_id = _require_user_uuid()
    nids = [int(x) for x in node_ids if int(x) > 0][:200]
    qh = (query_sha256 or "").strip().lower()
    if qh and len(qh) != 64:
        qh = qh[:64]
    m = meta if isinstance(meta, dict) else {}
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_memory_graph_activation_log (
                  tenant_id, user_id, dashboard_id, node_ids, query_sha256, meta
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (tenant_id, user_id, dashboard_id, nids, qh or None, Json(m)),
            )
            rid = cur.fetchone()
        conn.commit()
    return int(rid[0]) if rid else 0


def memory_graph_activation_log_list(*, limit: int = 100) -> list[dict[str, Any]]:
    tenant_id, user_id = _require_user_uuid()
    limit = max(1, min(int(limit or 100), 500))
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, dashboard_id, node_ids, query_sha256, meta, created_at
                FROM user_memory_graph_activation_log
                WHERE tenant_id = %s AND user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (tenant_id, user_id, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        w = r.get("dashboard_id")
        out.append(
            {
                "id": int(r["id"]),
                "dashboard_id": str(w) if w else None,
                "node_ids": [int(x) for x in (r.get("node_ids") or [])],
                "query_sha256": r.get("query_sha256"),
                "meta": r.get("meta") if isinstance(r.get("meta"), dict) else {},
                "created_at": r["created_at"].isoformat() if r.get("created_at") else "",
            }
        )
    return out


def rag_document_and_chunks_insert(
    tenant_id: int,
    user_id: uuid.UUID,
    domain: str,
    title: str,
    source_uri: str | None,
    content_sha256: str,
    chunks: list[tuple[int, str, list[float]]],
    *,
    workspace_id: uuid.UUID | None = None,
) -> tuple[int, int]:
    """
    Insert one ``rag_documents`` row and its chunks (each with embedding).
    Returns ``(document_id, chunk_count)``. Caller must validate embedding dims.
    """
    if not chunks:
        raise ValueError("chunks must be non-empty")
    domain = (domain or "").strip()
    title = (title or "").strip()
    uri = (source_uri or "").strip() or None
    sha = (content_sha256 or "").strip() or None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO rag_documents
                  (tenant_id, user_id, workspace_id, domain, title, source_uri, content_sha256)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tenant_id, user_id, workspace_id, domain, title, uri, sha),
            )
            doc_id = int(cur.fetchone()[0])
            for idx, content, emb in chunks:
                cur.execute(
                    """
                    INSERT INTO rag_chunks (document_id, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s::vector)
                    """,
                    (doc_id, int(idx), content, _vector_literal(emb)),
                )
        conn.commit()
    return doc_id, len(chunks)


def rag_delete_documents_by_workspace(tenant_id: int, workspace_id: uuid.UUID) -> int:
    """Delete all RAG documents for a workspace (cascades to chunks)."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_documents
                WHERE tenant_id = %s AND workspace_id = %s
                """,
                (tenant_id, workspace_id),
            )
            n = cur.rowcount or 0
        conn.commit()
    return int(n)


def rag_documents_by_tenant_domain_index(
    tenant_id: int,
    domain: str,
    *,
    workspace_id: uuid.UUID | None = None,
) -> dict[str, dict[str, Any]]:
    """``source_uri`` → ``{id, content_sha256}`` for incremental ingest."""
    dom = (domain or "").strip().lower()
    if not dom:
        return {}
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if workspace_id is None:
                cur.execute(
                    """
                    SELECT id, source_uri, content_sha256
                    FROM rag_documents
                    WHERE tenant_id = %s
                      AND lower(trim(domain)) = %s
                      AND workspace_id IS NULL
                      AND source_uri IS NOT NULL
                      AND trim(source_uri) <> ''
                    """,
                    (tenant_id, dom),
                )
            else:
                cur.execute(
                    """
                    SELECT id, source_uri, content_sha256
                    FROM rag_documents
                    WHERE tenant_id = %s
                      AND lower(trim(domain)) = %s
                      AND workspace_id = %s
                      AND source_uri IS NOT NULL
                      AND trim(source_uri) <> ''
                    """,
                    (tenant_id, dom, workspace_id),
                )
            rows = cur.fetchall()
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        uri = str(r.get("source_uri") or "").strip()
        if not uri:
            continue
        out[uri] = {
            "id": int(r["id"]),
            "content_sha256": (str(r.get("content_sha256") or "").strip() or None),
        }
    return out


def rag_delete_document_by_id(document_id: int) -> bool:
    """Delete one document and its chunks."""
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_documents WHERE id = %s", (int(document_id),))
            n = cur.rowcount or 0
        conn.commit()
    return n > 0


def rag_delete_documents_by_tenant_domain(tenant_id: int, domain: str) -> int:
    """Delete all ``rag_documents`` for a tenant and domain (case-insensitive). Cascades to chunks."""
    dom = (domain or "").strip().lower()
    if not dom:
        return 0
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM rag_documents
                WHERE tenant_id = %s AND lower(trim(domain)) = %s
                """,
                (tenant_id, dom),
            )
            n = cur.rowcount or 0
        conn.commit()
    return int(n)


def rag_vector_search_by_workspace(
    tenant_id: int,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    """Cosine search over chunks whose document belongs to ``workspace_id`` only."""
    limit = max(1, min(int(limit), 50))
    qv = _vector_literal(query_embedding)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  c.id AS chunk_id,
                  c.chunk_index,
                  left(c.content, 8000) AS content,
                  d.id AS document_id,
                  d.title,
                  d.domain,
                  d.source_uri,
                  (c.embedding <=> %s::vector) AS distance
                FROM rag_chunks c
                JOIN rag_documents d ON d.id = c.document_id
                WHERE d.tenant_id = %s
                  AND d.user_id = %s
                  AND d.workspace_id = %s
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (qv, tenant_id, user_id, workspace_id, qv, limit),
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        dist = r.get("distance")
        out.append(
            {
                "chunk_id": r["chunk_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "document_id": r["document_id"],
                "title": r["title"],
                "domain": r["domain"],
                "source_uri": r.get("source_uri"),
                "distance": float(dist) if dist is not None else None,
            }
        )
    return out


def rag_vector_search(
    tenant_id: int,
    user_id: uuid.UUID,
    query_embedding: list[float],
    domain: str | None,
    limit: int,
    *,
    tenant_wide_domain: bool = False,
) -> list[dict[str, Any]]:
    """Cosine distance (pgvector ``<=>``); lower is more similar."""
    limit = max(1, min(int(limit), 50))
    dom = (domain or "").strip()
    dom_lc = dom.lower()
    qv = _vector_literal(query_embedding)
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if tenant_wide_domain:
                if not dom_lc:
                    rows = []
                else:
                    cur.execute(
                        """
                        SELECT
                          c.id AS chunk_id,
                          c.chunk_index,
                          left(c.content, 8000) AS content,
                          d.id AS document_id,
                          d.title,
                          d.domain,
                          (c.embedding <=> %s::vector) AS distance
                        FROM rag_chunks c
                        JOIN rag_documents d ON d.id = c.document_id
                        WHERE d.tenant_id = %s
                          AND d.workspace_id IS NULL
                          AND lower(trim(d.domain)) = %s
                        ORDER BY c.embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (qv, tenant_id, dom_lc, qv, limit),
                    )
                    rows = cur.fetchall()
            else:
                cur.execute(
                    """
                    SELECT
                      c.id AS chunk_id,
                      c.chunk_index,
                      left(c.content, 8000) AS content,
                      d.id AS document_id,
                      d.title,
                      d.domain,
                      (c.embedding <=> %s::vector) AS distance
                    FROM rag_chunks c
                    JOIN rag_documents d ON d.id = c.document_id
                    WHERE d.tenant_id = %s
                      AND d.user_id = %s
                      AND d.workspace_id IS NULL
                      AND (%s = '' OR d.domain = %s)
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (qv, tenant_id, user_id, dom, dom, qv, limit),
                )
                rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        dist = r.get("distance")
        out.append(
            {
                "chunk_id": r["chunk_id"],
                "chunk_index": r["chunk_index"],
                "content": r["content"],
                "document_id": r["document_id"],
                "title": r["title"],
                "domain": r["domain"],
                "distance": float(dist) if dist is not None else None,
            }
        )
    return out


def user_persona_get(user_id: uuid.UUID) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT instructions, inject_into_agent, updated_at
                FROM user_agent_persona
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return {
        "instructions": row["instructions"] or "",
        "inject_into_agent": bool(row["inject_into_agent"]),
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def user_persona_upsert(
    tenant_id: int,
    user_id: uuid.UUID,
    *,
    instructions: str,
    inject_into_agent: bool,
) -> None:
    text = (instructions or "").strip()
    if len(text) > 100_000:
        raise ValueError("instructions too long (max 100000 characters)")
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_agent_persona (user_id, tenant_id, instructions, inject_into_agent)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  instructions = EXCLUDED.instructions,
                  inject_into_agent = EXCLUDED.inject_into_agent,
                  updated_at = now()
                """,
                (user_id, tenant_id, text, inject_into_agent),
            )
        conn.commit()


DEFAULT_AGENT_PROFILE: dict[str, Any] = {
    "display_name": "",
    "preferred_output_language": "",
    "locale": "",
    "timezone": "",
    "home_location": "",
    "work_location": "",
    "travel_mode": "",
    "travel_preferences": {},
    "tone": "",
    "verbosity": "",
    "language_level": "",
    "interests": [],
    "hobbies": [],
    "job_title": "",
    "organization": "",
    "industry": "",
    "experience_level": "",
    "primary_tools": [],
    "proactive_mode": False,
    "interaction_style": "",
    "inject_structured_profile": True,
    "inject_dynamic_traits": False,
    "dynamic_traits": {},
    "profile_version": 0,
    "profile_hash": "",
    "injection_preferences": {},
    "usage_patterns": {},
}

# Fields that define profile content for profile_hash (cache / diff).
_PROFILE_HASH_FIELDS: tuple[str, ...] = (
    "display_name",
    "preferred_output_language",
    "locale",
    "timezone",
    "home_location",
    "work_location",
    "travel_mode",
    "travel_preferences",
    "tone",
    "verbosity",
    "language_level",
    "interests",
    "hobbies",
    "job_title",
    "organization",
    "industry",
    "experience_level",
    "primary_tools",
    "proactive_mode",
    "interaction_style",
    "inject_structured_profile",
    "inject_dynamic_traits",
    "dynamic_traits",
    "injection_preferences",
    "usage_patterns",
)


def _compute_profile_hash(d: dict[str, Any]) -> str:
    payload = {k: d[k] for k in _PROFILE_HASH_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _norm_json_array(val: Any) -> list[Any]:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            p = json.loads(val)
            return p if isinstance(p, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _norm_json_object(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str) and val.strip():
        try:
            p = json.loads(val)
            return p if isinstance(p, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _norm_weighted_tags(val: Any) -> list[dict[str, Any]]:
    """Interests/hobbies: strings or ``[{ \"name\": \"…\", \"weight\": 0.0–1.0 }]``."""
    out: list[dict[str, Any]] = []
    items: list[Any]
    if isinstance(val, list):
        items = val
    else:
        items = _norm_json_array(val)
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "weight": 1.0})
        elif isinstance(item, dict):
            n = str(item.get("name") or "").strip()
            if not n:
                continue
            try:
                w = float(item.get("weight", 1.0))
            except (TypeError, ValueError):
                w = 1.0
            w = max(0.0, min(1.0, w))
            out.append({"name": n, "weight": w})
    return out[:200]


def _row_to_agent_profile(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_name": row.get("display_name") or "",
        "preferred_output_language": row.get("preferred_output_language") or "",
        "locale": row.get("locale") or "",
        "timezone": row.get("timezone") or "",
        "home_location": row.get("home_location") or "",
        "work_location": row.get("work_location") or "",
        "travel_mode": row.get("travel_mode") or "",
        "travel_preferences": _norm_json_object(row.get("travel_preferences")),
        "tone": row.get("tone") or "",
        "verbosity": row.get("verbosity") or "",
        "language_level": row.get("language_level") or "",
        "interests": _norm_weighted_tags(row.get("interests")),
        "hobbies": _norm_weighted_tags(row.get("hobbies")),
        "job_title": row.get("job_title") or "",
        "organization": row.get("organization") or "",
        "industry": row.get("industry") or "",
        "experience_level": row.get("experience_level") or "",
        "primary_tools": _norm_json_array(row.get("primary_tools")),
        "proactive_mode": bool(row.get("proactive_mode")),
        "interaction_style": row.get("interaction_style") or "",
        "inject_structured_profile": bool(row.get("inject_structured_profile", True)),
        "inject_dynamic_traits": bool(row.get("inject_dynamic_traits")),
        "dynamic_traits": _norm_json_object(row.get("dynamic_traits")),
        "profile_version": int(row.get("profile_version") or 0),
        "profile_hash": str(row.get("profile_hash") or ""),
        "injection_preferences": _norm_json_object(row.get("injection_preferences")),
        "usage_patterns": _norm_json_object(row.get("usage_patterns")),
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def user_timezone_persist(
    tenant_id: int,
    user_id: uuid.UUID,
    timezone_name: str,
) -> None:
    """Save IANA timezone from browser/client — used by chat and background jobs for this user."""
    tz = (timezone_name or "").strip()
    if not tz or len(tz) > 128:
        return
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_agent_profile (user_id, tenant_id, timezone)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                  timezone = EXCLUDED.timezone,
                  updated_at = now()
                WHERE user_agent_profile.timezone IS DISTINCT FROM EXCLUDED.timezone
                """,
                (user_id, tenant_id, tz),
            )
        conn.commit()


def user_agent_profile_get(user_id: uuid.UUID) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                  display_name, preferred_output_language, locale, timezone,
                  home_location, work_location, travel_mode, travel_preferences,
                  tone, verbosity, language_level,
                  interests, hobbies,
                  job_title, organization, industry, experience_level, primary_tools,
                  proactive_mode, interaction_style,
                  inject_structured_profile, inject_dynamic_traits, dynamic_traits,
                  profile_version, profile_hash, injection_preferences, usage_patterns,
                  updated_at
                FROM user_agent_profile
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return _row_to_agent_profile(row)


def user_agent_profile_upsert(
    tenant_id: int,
    user_id: uuid.UUID,
    data: dict[str, Any],
) -> None:
    """Replace structured profile for user (complete row). Bumps profile_version; sets profile_hash."""
    d = {**DEFAULT_AGENT_PROFILE, **data}
    d.pop("profile_version", None)
    d.pop("profile_hash", None)
    d["travel_preferences"] = _norm_json_object(d.get("travel_preferences"))
    d["interests"] = _norm_weighted_tags(d.get("interests"))
    d["hobbies"] = _norm_weighted_tags(d.get("hobbies"))
    d["primary_tools"] = _norm_json_array(d.get("primary_tools"))
    d["dynamic_traits"] = _norm_json_object(d.get("dynamic_traits"))
    d["injection_preferences"] = _norm_json_object(d.get("injection_preferences"))
    d["usage_patterns"] = _norm_json_object(d.get("usage_patterns"))
    d["proactive_mode"] = bool(d.get("proactive_mode"))
    d["inject_structured_profile"] = bool(d.get("inject_structured_profile", True))
    d["inject_dynamic_traits"] = bool(d.get("inject_dynamic_traits"))
    for arr_name in ("interests", "hobbies", "primary_tools"):
        if len(d[arr_name]) > 200:
            raise ValueError(f"{arr_name}: at most 200 entries")
    if len(json.dumps(d["travel_preferences"])) > 16_000:
        raise ValueError("travel_preferences JSON too large")
    if len(json.dumps(d["dynamic_traits"])) > 16_000:
        raise ValueError("dynamic_traits JSON too large")
    if len(json.dumps(d["injection_preferences"])) > 16_000:
        raise ValueError("injection_preferences JSON too large")
    if len(json.dumps(d["usage_patterns"])) > 16_000:
        raise ValueError("usage_patterns JSON too large")
    for k in (
        "display_name",
        "preferred_output_language",
        "locale",
        "timezone",
        "home_location",
        "work_location",
        "travel_mode",
        "tone",
        "verbosity",
        "language_level",
        "job_title",
        "organization",
        "industry",
        "experience_level",
        "interaction_style",
    ):
        s = str(d.get(k) or "")
        if len(s) > 10_000:
            raise ValueError(f"{k} too long (max 10000 characters)")
    phash = _compute_profile_hash(d)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT profile_version FROM user_agent_profile WHERE user_id = %s",
                (user_id,),
            )
            prev = cur.fetchone()
            old_v = int(prev[0]) if prev else 0
            new_v = old_v + 1
            cur.execute(
                """
                INSERT INTO user_agent_profile (
                  user_id, tenant_id,
                  display_name, preferred_output_language, locale, timezone,
                  home_location, work_location, travel_mode, travel_preferences,
                  tone, verbosity, language_level,
                  interests, hobbies,
                  job_title, organization, industry, experience_level, primary_tools,
                  proactive_mode, interaction_style,
                  inject_structured_profile, inject_dynamic_traits, dynamic_traits,
                  profile_version, profile_hash, injection_preferences, usage_patterns
                )
                VALUES (
                  %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s, %s,
                  %s, %s, %s,
                  %s, %s,
                  %s, %s, %s, %s, %s,
                  %s, %s,
                  %s, %s, %s,
                  %s, %s, %s, %s
                )
                ON CONFLICT (user_id) DO UPDATE SET
                  tenant_id = EXCLUDED.tenant_id,
                  display_name = EXCLUDED.display_name,
                  preferred_output_language = EXCLUDED.preferred_output_language,
                  locale = EXCLUDED.locale,
                  timezone = EXCLUDED.timezone,
                  home_location = EXCLUDED.home_location,
                  work_location = EXCLUDED.work_location,
                  travel_mode = EXCLUDED.travel_mode,
                  travel_preferences = EXCLUDED.travel_preferences,
                  tone = EXCLUDED.tone,
                  verbosity = EXCLUDED.verbosity,
                  language_level = EXCLUDED.language_level,
                  interests = EXCLUDED.interests,
                  hobbies = EXCLUDED.hobbies,
                  job_title = EXCLUDED.job_title,
                  organization = EXCLUDED.organization,
                  industry = EXCLUDED.industry,
                  experience_level = EXCLUDED.experience_level,
                  primary_tools = EXCLUDED.primary_tools,
                  proactive_mode = EXCLUDED.proactive_mode,
                  interaction_style = EXCLUDED.interaction_style,
                  inject_structured_profile = EXCLUDED.inject_structured_profile,
                  inject_dynamic_traits = EXCLUDED.inject_dynamic_traits,
                  dynamic_traits = EXCLUDED.dynamic_traits,
                  profile_version = EXCLUDED.profile_version,
                  profile_hash = EXCLUDED.profile_hash,
                  injection_preferences = EXCLUDED.injection_preferences,
                  usage_patterns = EXCLUDED.usage_patterns,
                  updated_at = now()
                """,
                (
                    user_id,
                    tenant_id,
                    d["display_name"],
                    d["preferred_output_language"],
                    d["locale"],
                    d["timezone"],
                    d["home_location"],
                    d["work_location"],
                    d["travel_mode"],
                    Json(d["travel_preferences"]),
                    d["tone"],
                    d["verbosity"],
                    d["language_level"],
                    Json(d["interests"]),
                    Json(d["hobbies"]),
                    d["job_title"],
                    d["organization"],
                    d["industry"],
                    d["experience_level"],
                    Json(d["primary_tools"]),
                    d["proactive_mode"],
                    d["interaction_style"],
                    d["inject_structured_profile"],
                    d["inject_dynamic_traits"],
                    Json(d["dynamic_traits"]),
                    new_v,
                    phash,
                    Json(d["injection_preferences"]),
                    Json(d["usage_patterns"]),
                ),
            )
        conn.commit()


def user_resolve_in_tenant(
    tenant_id: int,
    *,
    email: str | None = None,
    external_sub: str | None = None,
) -> uuid.UUID | None:
    em = (email or "").strip()
    sub = (external_sub or "").strip()
    if not em and not sub:
        return None
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if em:
                cur.execute(
                    """
                    SELECT id FROM users
                    WHERE tenant_id = %s AND email IS NOT NULL
                      AND lower(trim(email)) = lower(trim(%s))
                    """,
                    (tenant_id, em),
                )
            else:
                cur.execute(
                    "SELECT id FROM users WHERE tenant_id = %s AND external_sub = %s",
                    (tenant_id, sub),
                )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    uid = row[0]
    return uid if isinstance(uid, uuid.UUID) else uuid.UUID(str(uid))


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


def external_llm_endpoints_list_all() -> list[dict[str, Any]]:
    """All external LLM endpoints (admin); includes ``api_key`` — do not expose to non-admin JSON."""
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, sort_order, enabled, label, base_url, api_key,
                       model_default, model_vlm, model_agent, model_coding,
                       created_at, updated_at
                FROM operator_external_llm_endpoints
                ORDER BY sort_order ASC, id ASC
                """
            )
            rows = cur.fetchall()
        conn.commit()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at"):
            v = d.get(k)
            if v is not None and hasattr(v, "isoformat"):
                d[k] = v.isoformat()
        d["id"] = int(d["id"])
        d["sort_order"] = int(d["sort_order"])
        d["enabled"] = bool(d["enabled"])
        out.append(d)
    return out


def external_llm_endpoints_enabled_ordered() -> list[dict[str, Any]]:
    """Enabled rows only, same order as :func:`external_llm_endpoints_list_all`."""
    return [r for r in external_llm_endpoints_list_all() if r.get("enabled")]


def external_llm_endpoint_by_id(endpoint_id: int) -> dict[str, Any] | None:
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT id, sort_order, enabled, label, base_url, api_key,
                       model_default, model_vlm, model_agent, model_coding,
                       created_at, updated_at
                FROM operator_external_llm_endpoints
                WHERE id = %s
                """,
                (int(endpoint_id),),
            )
            r = cur.fetchone()
        conn.commit()
    if not r:
        return None
    d = dict(r)
    d["id"] = int(d["id"])
    d["sort_order"] = int(d["sort_order"])
    d["enabled"] = bool(d["enabled"])
    return d


def external_llm_endpoints_sync(rows: list[dict[str, Any]]) -> None:
    """
    Replace endpoint set: update existing by ``id``, insert rows without ``id``,
    delete DB rows whose ``id`` is not listed. Empty ``api_key`` on update keeps the stored key.
    """
    incoming_ids: set[int] = set()
    for raw in rows:
        i = raw.get("id")
        if i is not None:
            incoming_ids.add(int(i))

    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM operator_external_llm_endpoints")
            existing = {int(r[0]) for r in cur.fetchall()}
            for eid in existing - incoming_ids:
                cur.execute(
                    "DELETE FROM operator_external_llm_endpoints WHERE id = %s",
                    (eid,),
                )

            for raw in rows:
                sid = raw.get("sort_order")
                sort_order = int(sid) if sid is not None else 0
                enabled = bool(raw.get("enabled", True))
                label = str(raw.get("label") or "")[:512]
                base_url = str(raw.get("base_url") or "").strip()
                key_in = raw.get("api_key")
                md = raw.get("model_default")
                mv = raw.get("model_vlm")
                ma = raw.get("model_agent")
                mc = raw.get("model_coding")
                md_v = (str(md).strip() if md is not None else None) or None
                mv_v = (str(mv).strip() if mv is not None else None) or None
                ma_v = (str(ma).strip() if ma is not None else None) or None
                mc_v = (str(mc).strip() if mc is not None else None) or None

                rid = raw.get("id")
                if rid is None:
                    if not base_url:
                        raise ValueError("external_llm: base_url required for new endpoint")
                    nk = (str(key_in).strip() if key_in is not None else "")
                    cur.execute(
                        """
                        INSERT INTO operator_external_llm_endpoints (
                          sort_order, enabled, label, base_url, api_key,
                          model_default, model_vlm, model_agent, model_coding, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                        """,
                        (
                            sort_order,
                            enabled,
                            label,
                            base_url,
                            nk,
                            md_v,
                            mv_v,
                            ma_v,
                            mc_v,
                        ),
                    )
                else:
                    eid = int(rid)
                    cur.execute(
                        "SELECT api_key FROM operator_external_llm_endpoints WHERE id = %s",
                        (eid,),
                    )
                    prev = cur.fetchone()
                    if not prev:
                        raise ValueError(f"external_llm: unknown id {eid}")
                    prev_key = str(prev[0] or "")
                    if key_in is None or (isinstance(key_in, str) and not key_in.strip()):
                        key_use = prev_key
                    else:
                        key_use = str(key_in).strip()
                    if not base_url or not key_use:
                        raise ValueError("external_llm: base_url and api_key required")
                    cur.execute(
                        """
                        UPDATE operator_external_llm_endpoints SET
                          sort_order = %s,
                          enabled = %s,
                          label = %s,
                          base_url = %s,
                          api_key = %s,
                          model_default = %s,
                          model_vlm = %s,
                          model_agent = %s,
                          model_coding = %s,
                          updated_at = now()
                        WHERE id = %s
                        """,
                        (
                            sort_order,
                            enabled,
                            label,
                            base_url,
                            key_use,
                            md_v,
                            mv_v,
                            ma_v,
                            mc_v,
                            eid,
                        ),
                    )
        conn.commit()