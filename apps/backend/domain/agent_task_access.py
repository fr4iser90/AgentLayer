"""Authorization for agent tasks and artifacts (tenant + workspace)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.infrastructure.workspace_service import ensure_workspace


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
