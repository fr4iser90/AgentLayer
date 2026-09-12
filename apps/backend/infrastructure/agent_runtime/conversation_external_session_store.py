"""Per-conversation external runtime binding (``schema_127``).

One conversation maps to one vendor-native session (Qwen Code ``--resume <id>``), so the
same coding session continues across turns of a thread instead of starting cold and
re-reading the repository every time.
"""

from __future__ import annotations

import logging
import uuid

from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


def get_conversation_external_session(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> tuple[str | None, str | None]:
    """Return ``(runtime_id, session_id)`` for this conversation; ``(None, None)`` when unset.

    Shared threads are deliberately excluded (same rule as the goal store): a session
    belongs to the person who started it.
    """
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT external_runtime, external_session_id
                    FROM chat_conversations
                    WHERE id = %s AND user_id = %s AND shared = false
                    """,
                    (conversation_id, user_id),
                )
                row = cur.fetchone()
    except Exception:
        logger.warning("external session lookup failed", exc_info=True)
        return (None, None)
    if not row:
        return (None, None)
    runtime = str(row[0]).strip() if row[0] else None
    session = str(row[1]).strip() if row[1] else None
    return (runtime, session)


def set_conversation_external_session(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    runtime: str,
    session_id: str | None,
) -> bool:
    """Store the runtime id and native session id; ``False`` when the row is not writable."""
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_conversations
                    SET external_runtime = %s, external_session_id = %s, updated_at = now()
                    WHERE id = %s AND user_id = %s AND shared = false
                    """,
                    (runtime, session_id, conversation_id, user_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
    except Exception:
        logger.warning("external session store failed", exc_info=True)
        return False
    return updated


__all__ = ["get_conversation_external_session", "set_conversation_external_session"]
