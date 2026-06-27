from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.plugins.mcp_runtime import _parse_servers_payload
from apps.backend.infrastructure.workspace import workspace_delegate_store, workspace_retrieval
from apps.backend.infrastructure.workspace.workspace_columns import WORKSPACE_SELECT_SQL, workspace_row_to_api
from apps.backend.infrastructure.workspace.workspace_git import (
    workspace_git_changes_summary,
    workspace_git_file_diff,
)
from apps.backend.infrastructure.workspace.workspace_index_policy import (
    normalize_index_on_write,
    parse_retrieve_context_sources,
)
from apps.backend.infrastructure.workspace.workspace_service import (
    AGENTLAYER_SELF_NAME,
    WorkspaceCreateError,
    create_implementation_git_branch,
    create_project_workspace_for_user,
    delete_owned_workspace,
    ensure_workspace,
    reset_agentlayer_self_workspace,
    self_editing_allowed,
    validate_workspace_name,
)


def row_to_workspace(row: tuple) -> dict[str, Any]:
    return workspace_row_to_api(row)


def workspace_base_path(default: str = "/workspace") -> Path:
    import os

    return Path(os.environ.get("AGENTLAYER_WORKSPACE_PATH", default))


def fetch_owned_workspace_rows(user_id: uuid.UUID) -> list[tuple]:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
                FROM project_workspaces
                WHERE owner_user_id = %s
                ORDER BY name ASC
                """,
                (user_id,),
            )
            return list(cur.fetchall())


def fetch_owned_workspace_row(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s
                """,
                (workspace_id, user_id),
            )
            return cur.fetchone()


def fetch_workspace_row_any_owner(workspace_id: str) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
                FROM project_workspaces
                WHERE id = %s
                """,
                (workspace_id,),
            )
            return cur.fetchone()


def fetch_editable_workspace_row(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + WORKSPACE_SELECT_SQL + """
                FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s AND access_role IN ('owner', 'editor')
                """,
                (workspace_id, user_id),
            )
            return cur.fetchone()


def fetch_owned_workspace_path_name(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT path, name FROM project_workspaces WHERE id = %s AND owner_user_id = %s",
                (workspace_id, user_id),
            )
            return cur.fetchone()


def fetch_editable_workspace_tenant_name(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tenant_id, name FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s AND access_role IN ('owner', 'editor')
                """,
                (workspace_id, user_id),
            )
            return cur.fetchone()


def fetch_owned_delete_workspace_name(workspace_id: str, user_id: uuid.UUID) -> tuple | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name FROM project_workspaces WHERE id = %s AND owner_user_id = %s AND access_role = 'owner'",
                (workspace_id, user_id),
            )
            return cur.fetchone()


def update_workspace_row(workspace_id: str, updates: list[str], params: list[Any]) -> None:
    if not updates:
        return
    values = list(params)
    values.append(workspace_id)
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE project_workspaces SET " + ", ".join(updates) + ", updated_at = NOW() WHERE id = %s",
                tuple(values),
            )
        conn.commit()


def encode_jsonb(value: Any) -> str:
    return json.dumps(value)
