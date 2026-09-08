"""ADR 0009: where a workspace's files live, and which server paths must refuse them."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.workspace.workspace_columns import (
    CLIENT_EXECUTION,
    normalize_execution_mode,
)

UNATTENDED_REFUSAL = (
    "This workspace runs on the client: unattended server-side jobs cannot reach "
    "its files (ADR 0009)."
)
BROWSE_REFUSAL = (
    "This workspace runs on the client: the server has no files to browse (ADR 0009)."
)
INDEX_REFUSAL = (
    "This workspace runs on the client: the server has no tree to index "
    "(ADR 0009, milestone 3)."
)


def is_client_execution(raw: Any) -> bool:
    return normalize_execution_mode(raw) == CLIENT_EXECUTION


def raise_if_client_workspace(workspace_id: Any, *, message: str = UNATTENDED_REFUSAL) -> None:
    """No-op when ``workspace_id`` is missing or the row is server-side / unknown.

    Unknown ids are left to the caller so a missing workspace still 404s instead of
    being reported as a client-placement problem.
    """
    if workspace_id is None:
        return
    wid = str(workspace_id).strip()
    if not wid:
        return
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT execution_mode FROM project_workspaces WHERE id = %s",
                (wid,),
            )
            row = cur.fetchone()
        conn.commit()
    if row and is_client_execution(row[0]):
        raise ValueError(message)


def raise_if_workflow_targets_client(workflow: dict[str, Any] | None) -> None:
    if not isinstance(workflow, dict):
        return
    raise_if_client_workspace(workflow.get("workspace_id"))
