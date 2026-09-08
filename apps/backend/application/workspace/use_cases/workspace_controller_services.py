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
from apps.backend.infrastructure.workspace.workspace_execution import (
    BROWSE_REFUSAL,
    INDEX_REFUSAL,
    is_client_execution,
)
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
    api = workspace_row_to_api(row)
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        effective_index_consent,
        operator_index_consent_max,
    )

    api["index_consent_effective"] = effective_index_consent(api)
    api["index_consent_operator_max"] = operator_index_consent_max()
    return api


def client_workspace_refusal(row: tuple | None, *, kind: str) -> str | None:
    """HTTP 400 detail when ``row`` is a client workspace; ``None`` otherwise."""
    if not row:
        return None
    api = workspace_row_to_api(row)
    if not is_client_execution(api.get("execution_mode")):
        return None
    return INDEX_REFUSAL if kind == "index" else BROWSE_REFUSAL


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


def crawl_index_consent_refusal(api: dict[str, Any], mode: str) -> str | None:
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        consent_refusal,
        mode_needs_consent,
    )

    return consent_refusal(api, mode_needs_consent(mode))


def normalize_index_consent_patch(raw: Any) -> str:
    """Raise ValueError with the HTTP 400 detail if the PATCH is invalid or above the operator cap."""
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        normalize_index_consent,
        refuse_if_above_operator_cap,
    )

    cap_err = refuse_if_above_operator_cap(raw)
    if cap_err:
        raise ValueError(cap_err)
    requested = normalize_index_consent(raw)
    if requested is None:
        raise ValueError("index_consent must be none, symbols, or text")
    return requested


def ingest_client_symbol_upload(
    workspace_id: str,
    api: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    replace_all: bool,
) -> dict[str, Any]:
    """Raise ValueError with the HTTP 400 detail when the workspace may not receive symbols."""
    from apps.backend.infrastructure.workspace.workspace_client_index import ingest_client_symbols
    from apps.backend.infrastructure.workspace.workspace_execution import is_client_execution
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        INDEX_CONSENT_SYMBOLS,
        consent_refusal,
    )

    if not is_client_execution(api.get("execution_mode")):
        raise ValueError(
            "This endpoint is for client workspaces. Use POST /v1/workspaces/{id}/index to crawl a server tree."
        )
    refused = consent_refusal(api, INDEX_CONSENT_SYMBOLS)
    if refused:
        raise ValueError(refused)
    if not api.get("semantic_index_enabled", True):
        raise ValueError("semantic_index_enabled is off for this workspace")
    return ingest_client_symbols(workspace_id, files, replace_all=replace_all)


def ingest_client_text_upload(
    workspace_id: str,
    api: dict[str, Any],
    documents: list[dict[str, Any]],
    *,
    purge_first: bool,
) -> dict[str, Any]:
    from apps.backend.infrastructure.workspace.workspace_client_index import ingest_client_text
    from apps.backend.infrastructure.workspace.workspace_execution import is_client_execution
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        INDEX_CONSENT_TEXT,
        consent_refusal,
    )

    if not is_client_execution(api.get("execution_mode")):
        raise ValueError(
            "This endpoint is for client workspaces. Use POST /v1/workspaces/{id}/index with mode=docs to crawl."
        )
    refused = consent_refusal(api, INDEX_CONSENT_TEXT)
    if refused:
        raise ValueError(refused)
    if not api.get("docs_rag_enabled", True):
        raise ValueError("docs_rag_enabled is off for this workspace")
    return ingest_client_text(workspace_id, documents, purge_first=purge_first)
