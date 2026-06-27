"""Resolve active tasks and clear orphan conversation bindings."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from apps.backend.domain.agent_runtime.task_access import user_may_access_task_row

logger = logging.getLogger(__name__)


class AgentRunPersistenceDependencies(Protocol):
    def get_task(self, *, task_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None: ...

    def clear_conversation_active_task(
        self,
        *,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None: ...


_deps: AgentRunPersistenceDependencies | None = None


def register_agent_run_persistence_dependencies(deps: AgentRunPersistenceDependencies) -> None:
    global _deps
    _deps = deps


class _AgentTasksStorePort:
    def get_task(self, *, task_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
        return _deps.get_task(task_id=task_id, tenant_id=tenant_id) if _deps is not None else None


agent_tasks_store = _AgentTasksStorePort()


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
        if _deps is not None:
            _deps.clear_conversation_active_task(
                conversation_id=conversation_id,
                user_id=user_id,
            )
    except Exception:
        logger.warning(
            "failed to clear orphan active_task_id on conversation %s",
            conversation_id,
            exc_info=True,
        )
