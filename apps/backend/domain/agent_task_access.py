"""Authorization for agent tasks and artifacts (tenant + workspace)."""

from __future__ import annotations

import uuid
from typing import Any, Protocol


class AgentTaskAccessDependencies(Protocol):
    def ensure_workspace(self, workspace_id: str, user: Any) -> Any | None: ...


_deps: AgentTaskAccessDependencies | None = None


def register_agent_task_access_dependencies(deps: AgentTaskAccessDependencies) -> None:
    global _deps
    _deps = deps


def ensure_workspace(workspace_id: str, user: Any) -> Any | None:
    return _deps.ensure_workspace(workspace_id, user) if _deps is not None else None


def user_may_access_workspace(*, user_id: uuid.UUID, workspace_id: uuid.UUID | str) -> bool:
    class _U:
        def __init__(self, uid: uuid.UUID) -> None:
            self.id = uid

    ws = ensure_workspace(str(workspace_id), _U(user_id))
    return ws is not None


def user_may_access_task_row(
    *,
    user_id: uuid.UUID,
    tenant_id: int,
    row: dict[str, Any],
) -> bool:
    if int(row.get("tenant_id") or 0) != int(tenant_id):
        return False
    if row.get("created_by_user_id") == user_id:
        return True
    wid = row.get("workspace_id")
    if wid is not None:
        return user_may_access_workspace(user_id=user_id, workspace_id=wid)
    return False
