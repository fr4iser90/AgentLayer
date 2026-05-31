"""Resolve active tasks and clear orphan conversation bindings."""

from __future__ import annotations

import logging
import uuid

from apps.backend.domain.agent_task_access import user_may_access_task_row
from apps.backend.infrastructure.db import db

logger = logging.getLogger(__name__)


def resolve_valid_active_task_id(
    *,
    tenant_id: int,
    user_id: uuid.UUID,
    candidate: str | None,
) -> tuple[str | None, uuid.UUID | None]:
    """Return (active_task_id, task_uuid) when the task exists and is accessible."""
    if not candidate or not str(candidate).strip():
        return None, None
    raw = str(candidate).strip()
    try:
        task_uuid = uuid.UUID(raw)
    except (ValueError, TypeError):
        logger.warning("ignoring invalid active_task_id %r", raw)
        return None, None
    from apps.backend.infrastructure import agent_tasks_store

    row = agent_tasks_store.get_task(task_id=task_uuid, tenant_id=tenant_id)
    if not row or not user_may_access_task_row(
        user_id=user_id, tenant_id=tenant_id, row=row
    ):
        logger.warning(
            "ignoring missing or inaccessible active_task_id %s (tenant=%s user=%s)",
            task_uuid,
            tenant_id,
            user_id,
        )
        return None, None
    return raw, task_uuid


def clear_conversation_active_task(
    *, conversation_id: uuid.UUID, user_id: uuid.UUID
) -> None:
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE chat_conversations
                    SET active_task_id = NULL, updated_at = now()
                    WHERE id = %s AND user_id = %s AND active_task_id IS NOT NULL
                    """,
                    (conversation_id, user_id),
                )
            conn.commit()
    except Exception:
        logger.warning(
            "failed to clear orphan active_task_id on conversation %s",
            conversation_id,
            exc_info=True,
        )
