"""Chat conversation storage and session quotas (operator_settings)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import _invalidate

logger = logging.getLogger(__name__)

DEFAULT_MAX_CONVERSATION_MB = 2048
DEFAULT_MAX_PERSONAL_SESSIONS = 100
DEFAULT_MAX_DASHBOARD_SESSIONS = 30
CHAT_WARN_RATIO = 0.8


def _operator_chat_quota_row() -> dict[str, Any]:
    empty = {
        "chat_max_conversation_mb": DEFAULT_MAX_CONVERSATION_MB,
        "chat_max_personal_sessions": DEFAULT_MAX_PERSONAL_SESSIONS,
        "chat_max_dashboard_sessions": DEFAULT_MAX_DASHBOARD_SESSIONS,
    }
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT chat_max_conversation_mb,
                           chat_max_personal_sessions,
                           chat_max_dashboard_sessions
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        logger.debug("chat quota row read failed", exc_info=True)
        return dict(empty)
    if not row:
        return dict(empty)

    def _pos_int(raw: Any, default: int) -> int:
        try:
            n = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default
        return n if n > 0 else default

    return {
        "chat_max_conversation_mb": _pos_int(row[0], DEFAULT_MAX_CONVERSATION_MB),
        "chat_max_personal_sessions": _pos_int(row[1], DEFAULT_MAX_PERSONAL_SESSIONS),
        "chat_max_dashboard_sessions": _pos_int(row[2], DEFAULT_MAX_DASHBOARD_SESSIONS),
    }


def chat_quota_settings_public_fields() -> dict[str, Any]:
    op = _operator_chat_quota_row()
    return {
        "chat_max_conversation_mb": op["chat_max_conversation_mb"],
        "chat_max_personal_sessions": op["chat_max_personal_sessions"],
        "chat_max_dashboard_sessions": op["chat_max_dashboard_sessions"],
        "chat_warn_ratio": CHAT_WARN_RATIO,
    }


def apply_chat_quota_operator_patch(patch: dict[str, Any]) -> None:
    keys = (
        "chat_max_conversation_mb",
        "chat_max_personal_sessions",
        "chat_max_dashboard_sessions",
    )
    if not any(k in patch for k in keys):
        return
    cur = _operator_chat_quota_row()
    out = dict(cur)

    def _apply_int(key: str, lo: int, hi: int) -> None:
        if key not in patch:
            return
        v = patch[key]
        if v is None:
            return
        try:
            n = int(v)
        except (TypeError, ValueError):
            return
        out[key] = max(lo, min(hi, n))

    _apply_int("chat_max_conversation_mb", 1, 50_000)
    _apply_int("chat_max_personal_sessions", 1, 10_000)
    _apply_int("chat_max_dashboard_sessions", 1, 10_000)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operator_settings SET
                  chat_max_conversation_mb = %s,
                  chat_max_personal_sessions = %s,
                  chat_max_dashboard_sessions = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (
                    out["chat_max_conversation_mb"],
                    out["chat_max_personal_sessions"],
                    out["chat_max_dashboard_sessions"],
                ),
            )
        conn.commit()
    _invalidate()


def max_conversation_bytes() -> int:
    mb = int(_operator_chat_quota_row()["chat_max_conversation_mb"])
    return max(1, mb) * 1024 * 1024


def conversation_used_bytes(conversation_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  COALESCE((
                    SELECT SUM(
                      octet_length(content)
                      + COALESCE(octet_length(reasoning), 0)
                    )
                    FROM chat_messages WHERE conversation_id = %s
                  ), 0)
                  + COALESCE((
                    SELECT pg_column_size(agent_log)
                    FROM chat_conversations WHERE id = %s
                  ), 0)
                """,
                (conversation_id, conversation_id),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def estimate_payload_bytes(
    messages: list[dict[str, Any]] | None,
    agent_log: Any | None,
) -> int:
    total = 0
    if isinstance(messages, list):
        for m in messages:
            if not isinstance(m, dict):
                continue
            content = m.get("content")
            if content is None:
                raw = ""
            elif isinstance(content, str):
                raw = content
            else:
                try:
                    raw = json.dumps(content, ensure_ascii=False)
                except (TypeError, ValueError):
                    raw = str(content)
            total += len(raw.encode("utf-8"))
            reasoning = m.get("reasoning") or m.get("reasoning_content")
            if isinstance(reasoning, str) and reasoning:
                total += len(reasoning.encode("utf-8"))
    if agent_log is not None:
        try:
            total += len(json.dumps(agent_log, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError):
            pass
    return total


def storage_snapshot(conversation_id: uuid.UUID) -> dict[str, Any]:
    used = conversation_used_bytes(conversation_id)
    limit_b = max_conversation_bytes()
    ratio = (used / limit_b) if limit_b > 0 else 0.0
    return {
        "used_bytes": used,
        "limit_bytes": limit_b,
        "warn": ratio >= CHAT_WARN_RATIO,
        "over_limit": used > limit_b,
        "warn_ratio": CHAT_WARN_RATIO,
    }


def assert_conversation_size_allowed(
    *,
    conversation_id: uuid.UUID | None,
    messages: list[dict[str, Any]] | None,
    agent_log: Any | None,
) -> dict[str, Any]:
    """Raise ValueError if projected size exceeds limit. Returns storage snapshot for response."""
    limit_b = max_conversation_bytes()
    if conversation_id is not None and messages is None and agent_log is None:
        snap = storage_snapshot(conversation_id)
        if snap["over_limit"]:
            raise ValueError(
                f"conversation storage limit exceeded "
                f"({snap['used_bytes']} / {snap['limit_bytes']} bytes)"
            )
        return snap

    projected = estimate_payload_bytes(messages, agent_log)
    if conversation_id is not None and messages is None and agent_log is not None:
        # agent_log-only update: keep message bytes, replace agent_log estimate
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(
                      octet_length(content) + COALESCE(octet_length(reasoning), 0)
                    ), 0)
                    FROM chat_messages WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                )
                row = cur.fetchone()
        msg_bytes = int(row[0] or 0) if row else 0
        projected = msg_bytes + estimate_payload_bytes(None, agent_log)

    if projected > limit_b:
        raise ValueError(
            f"conversation storage limit exceeded ({projected} / {limit_b} bytes)"
        )
    ratio = (projected / limit_b) if limit_b > 0 else 0.0
    return {
        "used_bytes": projected,
        "limit_bytes": limit_b,
        "warn": ratio >= CHAT_WARN_RATIO,
        "over_limit": False,
        "warn_ratio": CHAT_WARN_RATIO,
    }


def count_personal_sessions(user_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM chat_conversations
                WHERE user_id = %s AND dashboard_id IS NULL AND shared = false
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def count_dashboard_sessions(dashboard_id: uuid.UUID) -> int:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM chat_conversations
                WHERE dashboard_id = %s
                """,
                (dashboard_id,),
            )
            row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def assert_session_create_allowed(
    user_id: uuid.UUID,
    *,
    dashboard_id: uuid.UUID | None,
) -> None:
    op = _operator_chat_quota_row()
    if dashboard_id is None:
        n = count_personal_sessions(user_id)
        max_n = int(op["chat_max_personal_sessions"])
        if n >= max_n:
            raise ValueError(
                f"personal chat session limit reached ({n}/{max_n}). "
                "Delete old chats or ask an admin to raise the limit."
            )
        return
    n = count_dashboard_sessions(dashboard_id)
    max_n = int(op["chat_max_dashboard_sessions"])
    if n >= max_n:
        raise ValueError(
            f"dashboard chat session limit reached ({n}/{max_n}). "
            "Delete old dashboard chats or ask an admin to raise the limit."
        )
