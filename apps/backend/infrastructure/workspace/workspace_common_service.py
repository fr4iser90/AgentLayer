"""Infrastructure adapter for shared workspace tool helpers."""

from __future__ import annotations

import uuid
from typing import Any

from apps.backend.domain.workspace import workspace_common as domain
from apps.backend.infrastructure.platform.conversations_db import conversation_replace
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.workspace.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api
from apps.backend.infrastructure.workspace.workspace_service import (
    AGENTLAYER_SELF_NAME,
    ensure_workspace,
    self_editing_allowed,
)


class _WorkspaceCommonDeps:
    workspace_select_sql = WORKSPACE_SELECT_SQL
    agentlayer_self_name = AGENTLAYER_SELF_NAME
    pool = staticmethod(db.pool)
    user_role = staticmethod(db.user_role)
    workspace_row_to_api = staticmethod(workspace_row_to_api)
    self_editing_allowed = staticmethod(self_editing_allowed)
    ensure_workspace = staticmethod(ensure_workspace)

    @staticmethod
    def conversation_replace(
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        *,
        title: str | None,
        mode: str | None,
        model: str | None,
        messages: list[dict[str, Any]] | None,
        agent_log: list[dict[str, Any]] | None,
        composer_prefs: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        return conversation_replace(
            user_id,
            conversation_id,
            title=title,
            mode=mode,
            model=model,
            messages=messages,
            agent_log=agent_log,
            composer_prefs=composer_prefs,
        )


domain.register_workspace_common_dependencies(_WorkspaceCommonDeps())

bind_workspace_in_context = domain.bind_workspace_in_context
dump = domain.dump
find_owned_git_workspace = domain.find_owned_git_workspace
find_workspace_by_name = domain.find_workspace_by_name
git_url_equivalence_key = domain.git_url_equivalence_key
list_workspaces_for_user = domain.list_workspaces_for_user
normalize_git_url = domain.normalize_git_url
persist_conversation_workspace = domain.persist_conversation_workspace
user_from_context = domain.user_from_context
