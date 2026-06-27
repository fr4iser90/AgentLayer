"""Infrastructure adapter for agent task workspace access."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.agent_runtime import task_access as domain
from apps.backend.infrastructure.workspace.workspace_service import ensure_workspace


class _AgentTaskAccessDeps:
    @staticmethod
    def ensure_workspace(workspace_id: str, user: Any) -> Any | None:
        return ensure_workspace(workspace_id, user)


domain.register_agent_task_access_dependencies(_AgentTaskAccessDeps())

user_may_access_task_row = domain.user_may_access_task_row
user_may_access_workspace = domain.user_may_access_workspace
