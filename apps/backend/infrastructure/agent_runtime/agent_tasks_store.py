"""CRUD for ``agent_tasks`` (global + workspace-scoped hierarchical tasks)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from psycopg.rows import dict_row
from psycopg.types.json import Json

from apps.backend.infrastructure.db import db

TaskScope = Literal["global", "workspace"]
TaskStatus = Literal[
    "draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"
]
TaskPriority = Literal["low", "normal", "high"]

_STATUSES: frozenset[str] = frozenset(
    {"draft", "planning", "queued", "in_progress", "blocked", "done", "cancelled"}
)
_PRIORITIES: frozenset[str] = frozenset({"low", "normal", "high"})


def _now() -> datetime:
    return datetime.now(UTC)


def row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, uuid.UUID):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def create_task(
    *,
    tenant_id: int,
    created_by_user_id: uuid.UUID,
    scope: TaskScope,
    goal: str,
    task_type: str = "general",
    workspace_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    blocked_by_task_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    status: TaskStatus = "draft",
    priority: TaskPriority = "normal",
    assigned_agent_id: str | None = None,
    source: str = "user",
    requirements: list[Any] | None = None,
    artifact_refs: list[Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if scope == "global" and workspace_id is not None:
        raise ValueError("global tasks cannot have workspace_id")
    if scope == "workspace" and workspace_id is None:
        raise ValueError("workspace tasks require workspace_id")
    st = status if status in _STATUSES else "draft"
    pr = priority if priority in _PRIORITIES else "normal"
    root_id: uuid.UUID | None = None
    if parent_task_id is not None:
        parent = get_task(task_id=parent_task_id, tenant_id=tenant_id)
        if not parent:
            raise ValueError("parent_task_id not found")
        root_raw = parent.get("root_task_id") or parent.get("id")
        if root_raw:
            root_id = uuid.UUID(str(root_raw))
        if scope == "workspace" and workspace_id is None and parent.get("workspace_id"):
            workspace_id = uuid.UUID(str(parent["workspace_id"]))
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO agent_tasks (
                  tenant_id, created_by_user_id, scope, workspace_id,
                  parent_task_id, root_task_id, blocked_by_task_id, conversation_id,
                  task_type, goal, status, priority, assigned_agent_id, source,
                  requirements, artifact_refs, metadata, updated_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, now()
                )
                RETURNING *
                """,
                (
                    tenant_id,
                    created_by_user_id,
                    scope,
                    workspace_id,
                    parent_task_id,
                    root_id,
                    blocked_by_task_id,
                    conversation_id,
                    (task_type or "general").strip()[:128],
                    (goal or "").strip()[:16000],
                    st,
                    pr,
                    (assigned_agent_id or "").strip()[:128] or None,
                    (source or "user").strip()[:64],
                    Json(list(requirements or [])),
                    Json([str(x) for x in (artifact_refs or [])]),
                    Json(dict(metadata or {})),
                ),
            )
            row = cur.fetchone()
            if row and row.get("root_task_id") is None:
                tid = row["id"]
                cur.execute(
                    "UPDATE agent_tasks SET root_task_id = %s WHERE id = %s",
                    (tid, tid),
                )
                cur.execute("SELECT * FROM agent_tasks WHERE id = %s", (tid,))
                row = cur.fetchone()
        conn.commit()
    return dict(row) if row else {}


def get_task(*, task_id: uuid.UUID, tenant_id: int) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM agent_tasks WHERE id = %s AND tenant_id = %s",
                (task_id, tenant_id),
            )
            row = cur.fetchone()
        conn.commit()
    return dict(row) if row else None


def update_task(
    *,
    task_id: uuid.UUID,
    tenant_id: int,
    status: TaskStatus | None = None,
    goal: str | None = None,
    priority: TaskPriority | None = None,
    assigned_agent_id: str | None = None,
    artifact_refs: list[str] | None = None,
    append_artifact_ref: str | None = None,
    requirements: list[Any] | None = None,
    metadata_patch: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    row = get_task(task_id=task_id, tenant_id=tenant_id)
    if not row:
        return None
    parts: list[str] = ["updated_at = now()"]
    args: list[Any] = []
    if status is not None and status in _STATUSES:
        parts.append("status = %s")
        args.append(status)
    if goal is not None:
        parts.append("goal = %s")
        args.append(goal.strip()[:16000])
    if priority is not None and priority in _PRIORITIES:
        parts.append("priority = %s")
        args.append(priority)
    if assigned_agent_id is not None:
        parts.append("assigned_agent_id = %s")
        args.append(assigned_agent_id.strip()[:128] or None)
    if requirements is not None:
        parts.append("requirements = %s")
        args.append(Json(list(requirements)))
    if artifact_refs is not None:
        parts.append("artifact_refs = %s")
        args.append(Json([str(x) for x in artifact_refs]))
    elif append_artifact_ref:
        refs = list(row.get("artifact_refs") or [])
        if not isinstance(refs, list):
            refs = []
        aid = str(append_artifact_ref).strip()
        if aid and aid not in refs:
            refs.append(aid)
        parts.append("artifact_refs = %s")
        args.append(Json(refs))
    if metadata_patch:
        meta = dict(row.get("metadata") or {})
        meta.update(metadata_patch)
        parts.append("metadata = %s")
        args.append(Json(meta))
    args.extend([task_id, tenant_id])
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # SECURITY: Column names in `parts` come from function parameters
            # (status, goal, priority, etc.) — not from user input.
            # All values are parameterized via %s placeholders.
            cur.execute(
                "UPDATE agent_tasks SET " + ', '.join(parts) + " WHERE id = %s AND tenant_id = %s RETURNING *",
                args,
            )
            updated = cur.fetchone()
        conn.commit()
    return dict(updated) if updated else None


def list_tasks(
    *,
    tenant_id: int,
    created_by_user_id: uuid.UUID | None = None,
    scope: TaskScope | None = None,
    workspace_id: uuid.UUID | None = None,
    parent_task_id: uuid.UUID | None = None,
    root_task_id: uuid.UUID | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    lim = max(1, min(200, int(limit)))
    where = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if created_by_user_id is not None:
        where.append("created_by_user_id = %s")
        params.append(created_by_user_id)
    if scope is not None:
        where.append("scope = %s")
        params.append(scope)
    if workspace_id is not None:
        where.append("workspace_id = %s")
        params.append(workspace_id)
    if parent_task_id is not None:
        where.append("parent_task_id = %s")
        params.append(parent_task_id)
    if root_task_id is not None:
        where.append("root_task_id = %s")
        params.append(root_task_id)
    if status and status in _STATUSES:
        where.append("status = %s")
        params.append(status)
    params.append(lim)
    sql = f"""
        SELECT * FROM agent_tasks
        WHERE {' AND '.join(where)}
        ORDER BY updated_at DESC
        LIMIT %s
    """
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def fetch_queued_tasks(*, limit: int = 10) -> list[dict[str, Any]]:
    """Queued root tasks for the background runner (oldest first)."""
    lim = max(1, min(50, int(limit)))
    sql = """
        SELECT * FROM agent_tasks
        WHERE status = 'queued'
          AND (parent_task_id IS NULL OR parent_task_id = id)
        ORDER BY updated_at ASC
        LIMIT %s
    """
    with db.pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (lim,))
            rows = cur.fetchall()
        conn.commit()
    return [dict(r) for r in rows]


def list_subtasks(
    *,
    tenant_id: int,
    parent_task_id: uuid.UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return list_tasks(
        tenant_id=tenant_id,
        parent_task_id=parent_task_id,
        limit=limit,
    )
