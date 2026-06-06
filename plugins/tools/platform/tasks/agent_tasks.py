"""Create, list, update tasks and fetch task artifacts."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable, cast

from apps.backend.domain.agent_task_access import (
    user_may_access_task_row,
    user_may_access_workspace,
)
from apps.backend.domain.identity import get_identity
from apps.backend.infrastructure import agent_artifacts_store, agent_tasks_store
from apps.backend.domain.task_approval import normalize_new_task_status
from apps.backend.infrastructure.db import db

__version__ = "1.0.0"
TOOL_ID = "tasks"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "agent_tasks"
TOOL_LABEL = "Tasks"
TOOL_DESCRIPTION = (
    "Manage hierarchical tasks (global or per-workspace backlog) and fetch task artifacts by id."
)
TOOL_TRIGGERS = ("task", "backlog", "artifact", "subtask")
TOOL_CAPABILITIES = ("task.read", "task.write", "artifact.read")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "task_create": {"min_role": "user", "capabilities": ("task.write",)},
    "task_list": {"min_role": "user", "capabilities": ("task.read",)},
    "task_update": {"min_role": "user", "capabilities": ("task.write",)},
    "artifact_get": {"min_role": "user", "capabilities": ("artifact.read",)},
}


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (int(tid), uid)


def task_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    idt = _identity()
    if not idt:
        return _err("not authenticated")
    tenant_id, user_id = idt
    scope = str(arguments.get("scope") or "global").strip().lower()
    if scope not in ("global", "workspace"):
        return _err("scope must be global or workspace")
    goal = str(arguments.get("goal") or "").strip()
    if not goal:
        return _err("goal is required")
    ws_id: uuid.UUID | None = None
    ws_raw = arguments.get("workspace_id")
    if ws_raw is not None and str(ws_raw).strip():
        try:
            ws_id = uuid.UUID(str(ws_raw).strip())
        except (ValueError, TypeError):
            return _err("invalid workspace_id")
        if not user_may_access_workspace(user_id=user_id, workspace_id=ws_id):
            return _err("workspace not accessible")
    parent_id: uuid.UUID | None = None
    if arguments.get("parent_task_id"):
        try:
            parent_id = uuid.UUID(str(arguments["parent_task_id"]).strip())
        except (ValueError, TypeError):
            return _err("invalid parent_task_id")
    conv_id: uuid.UUID | None = None
    ctx = context or {}
    if ctx.get("conversation_id"):
        try:
            conv_id = uuid.UUID(str(ctx["conversation_id"]).strip())
        except (ValueError, TypeError):
            pass
    try:
        role = db.user_role(user_id)
        eff_status, approval_hint = normalize_new_task_status(
            requested=str(arguments.get("status") or "draft"),
            user_role=role,
        )
        row = agent_tasks_store.create_task(
            tenant_id=tenant_id,
            created_by_user_id=user_id,
            scope=scope,  # type: ignore[arg-type]
            goal=goal,
            task_type=str(arguments.get("task_type") or "general"),
            workspace_id=ws_id,
            parent_task_id=parent_id,
            conversation_id=conv_id,
            status=eff_status,  # type: ignore[arg-type]
            priority=str(arguments.get("priority") or "normal"),  # type: ignore[arg-type]
            assigned_agent_id=str(arguments.get("assigned_agent_id") or "") or None,
            requirements=arguments.get("requirements") if isinstance(arguments.get("requirements"), list) else None,
            artifact_refs=arguments.get("artifact_refs") if isinstance(arguments.get("artifact_refs"), list) else None,
        )
    except ValueError as e:
        return _err(str(e))
    payload = {"task": agent_tasks_store.row_to_public(row)}
    if approval_hint:
        payload["approval_hint"] = approval_hint
    return _ok(payload)


def task_list(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    idt = _identity()
    if not idt:
        return _err("not authenticated")
    tenant_id, user_id = idt
    scope = arguments.get("scope")
    scope_s = str(scope).strip().lower() if scope is not None else None
    if scope_s and scope_s not in ("global", "workspace"):
        return _err("scope must be global or workspace")
    ws_id: uuid.UUID | None = None
    if arguments.get("workspace_id"):
        try:
            ws_id = uuid.UUID(str(arguments["workspace_id"]).strip())
        except (ValueError, TypeError):
            return _err("invalid workspace_id")
    parent_id: uuid.UUID | None = None
    if arguments.get("parent_task_id"):
        try:
            parent_id = uuid.UUID(str(arguments["parent_task_id"]).strip())
        except (ValueError, TypeError):
            return _err("invalid parent_task_id")
    rows = agent_tasks_store.list_tasks(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        scope=scope_s,  # type: ignore[arg-type]
        workspace_id=ws_id,
        parent_task_id=parent_id,
        status=str(arguments.get("status") or "").strip() or None,
        limit=int(arguments.get("limit") or 50),
    )
    if arguments.get("root_only") in (True, "true", "1", 1):
        rows = [r for r in rows if r.get("parent_task_id") is None]
    return _ok({"tasks": [agent_tasks_store.row_to_public(r) for r in rows]})


def task_update(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    idt = _identity()
    if not idt:
        return _err("not authenticated")
    tenant_id, user_id = idt
    raw_id = arguments.get("task_id")
    if not raw_id:
        return _err("task_id is required")
    try:
        task_id = uuid.UUID(str(raw_id).strip())
    except (ValueError, TypeError):
        return _err("invalid task_id")
    row = agent_tasks_store.get_task(task_id=task_id, tenant_id=tenant_id)
    if not row or not user_may_access_task_row(user_id=user_id, tenant_id=tenant_id, row=row):
        return _err("task not found")
    new_status = str(arguments["status"]).strip() if arguments.get("status") else None
    updated = agent_tasks_store.update_task(
        task_id=task_id,
        tenant_id=tenant_id,
        status=new_status,  # type: ignore[arg-type]
        goal=str(arguments["goal"]).strip() if arguments.get("goal") else None,
        priority=str(arguments["priority"]).strip() if arguments.get("priority") else None,  # type: ignore[arg-type]
        assigned_agent_id=str(arguments["assigned_agent_id"]) if "assigned_agent_id" in arguments else None,
        append_artifact_ref=str(arguments["append_artifact_ref"]).strip()
        if arguments.get("append_artifact_ref")
        else None,
    )
    if not updated:
        return _err("update failed")
    return _ok({"task": agent_tasks_store.row_to_public(updated)})


def artifact_get(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    idt = _identity()
    if not idt:
        return _err("not authenticated")
    tenant_id, user_id = idt
    raw_id = arguments.get("artifact_id")
    if not raw_id:
        return _err("artifact_id is required")
    try:
        aid = uuid.UUID(str(raw_id).strip())
    except (ValueError, TypeError):
        return _err("invalid artifact_id")
    row = agent_artifacts_store.get_artifact(artifact_id=aid, tenant_id=tenant_id)
    if not row:
        return _err("artifact not found")
    if row.get("created_by_user_id") != user_id:
        wid = row.get("workspace_id")
        if wid is None or not user_may_access_workspace(user_id=user_id, workspace_id=wid):
            return _err("artifact not found")
    return _ok({"artifact": agent_artifacts_store.row_to_public(row)})


HANDLERS: dict[str, Callable[..., str]] = {
    "task_create": cast(Callable[..., str], task_create),
    "task_list": cast(Callable[..., str], task_list),
    "task_update": cast(Callable[..., str], task_update),
    "artifact_get": cast(Callable[..., str], artifact_get),
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "task_create",
            "description": "Create a global or workspace-scoped agent task (backlog item).",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["global", "workspace"]},
                    "goal": {"type": "string"},
                    "workspace_id": {"type": "string"},
                    "parent_task_id": {"type": "string"},
                    "task_type": {"type": "string"},
                    "status": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                    "assigned_agent_id": {"type": "string"},
                    "requirements": {"type": "array", "items": {"type": "string"}},
                    "artifact_refs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_list",
            "description": "List your agent tasks (filter by scope, workspace, parent, status).",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["global", "workspace"]},
                    "workspace_id": {"type": "string"},
                    "parent_task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "root_only": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_update",
            "description": "Update task status, goal, priority, or link an artifact ref.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string"},
                    "goal": {"type": "string"},
                    "priority": {"type": "string"},
                    "assigned_agent_id": {"type": "string"},
                    "append_artifact_ref": {"type": "string"},
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "artifact_get",
            "description": "Load a persisted artifact by id (summary + content).",
            "parameters": {
                "type": "object",
                "properties": {"artifact_id": {"type": "string"}},
                "required": ["artifact_id"],
            },
        },
    },
]
