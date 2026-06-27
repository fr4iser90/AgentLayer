"""Infrastructure adapter for active agent task persistence helpers."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain import agent_run_persistence as domain
from apps.backend.infrastructure import agent_tasks_store
from apps.backend.infrastructure.db import db


class _AgentRunPersistenceDeps:
    @staticmethod
    def get_task(*, task_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        return agent_tasks_store.get_task(task_id=task_id, tenant_id=tenant_id)

    @staticmethod
    def clear_conversation_active_task(
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
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


domain.register_agent_run_persistence_dependencies(_AgentRunPersistenceDeps())

clear_conversation_active_task = domain.clear_conversation_active_task
resolve_valid_active_task_id = domain.resolve_valid_active_task_id
