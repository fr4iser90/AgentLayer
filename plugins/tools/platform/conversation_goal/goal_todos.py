"""Conversation goal: ongoing objective + ephemeral todos (not product agent_tasks)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.domain.agent_runtime.conversation_goal import (
    apply_goal_update,
    new_goal,
    normalize_todos,
    todo_counts,
)
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.agent_runtime import conversation_goal_store as store

__version__ = "1.0.0"
TOOL_ID = "conversation_goal"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "conversation_goal"
TOOL_LABEL = "Conversation goal, todos & plan mode"
TOOL_DESCRIPTION = (
    "Manage the current chat's ongoing goal, short todo list, and plan mode for this run. "
    "Use for multi-step work in this conversation. "
    "Do NOT use for durable backlog — use task_create/task_list for product tasks."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("conversation.goal", "conversation.todo", "conversation.plan")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "goal_get": {"min_role": "user", "capabilities": ("conversation.goal",)},
    "goal_create": {"min_role": "user", "capabilities": ("conversation.goal",)},
    "goal_update": {"min_role": "user", "capabilities": ("conversation.goal",)},
    "todo_write": {"min_role": "user", "capabilities": ("conversation.todo",)},
    "todo_read": {"min_role": "user", "capabilities": ("conversation.todo",)},
    "plan_mode_set": {"min_role": "user", "capabilities": ("conversation.plan",)},
    "exit_plan_mode": {"min_role": "user", "capabilities": ("conversation.plan",)},
}


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _parse_uuid(raw: Any) -> uuid.UUID | None:
    if raw is None:
        return None
    try:
        return uuid.UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def _require_conversation(
    arguments: dict[str, Any], context: dict[str, Any] | None
) -> tuple[uuid.UUID, uuid.UUID] | str:
    _tid, user_id = get_identity()
    if user_id is None:
        return "not authenticated"
    ctx = context or {}
    cid = _parse_uuid(arguments.get("conversation_id")) or _parse_uuid(ctx.get("conversation_id"))
    if cid is None:
        return "conversation_id required (open a saved chat thread)"
    return user_id, cid


def goal_get(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    row = store.get_conversation_goal(user_id, conv_id)
    if row is None:
        return _err("conversation not found")
    return _ok({"goal": row.get("goal"), "ws_event": "agent.goal", "goal_event": "get"})


def goal_create(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    row = store.get_conversation_goal(user_id, conv_id)
    if row is None:
        return _err("conversation not found")
    existing = row.get("goal")
    if isinstance(existing, dict) and str(existing.get("phase") or "") in ("active", "paused"):
        return _err("an active or paused goal already exists — update or complete it first")
    try:
        goal = new_goal(
            objective=str(arguments.get("objective") or ""),
            max_goal_rounds=arguments.get("max_goal_rounds"),
        )
    except ValueError as e:
        return _err(str(e))
    saved = store.set_session_goal(user_id, conv_id, goal)
    if saved is None:
        return _err("failed to save goal")
    return _ok({"goal": saved["goal"], "ws_event": "agent.goal", "goal_event": "create"})


def goal_update(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    row = store.get_conversation_goal(user_id, conv_id)
    if row is None:
        return _err("conversation not found")
    try:
        updated = apply_goal_update(
            row.get("goal") if isinstance(row.get("goal"), dict) else None,
            goal_id=str(arguments.get("goal_id") or ""),
            revision=int(arguments.get("revision") or 0),
            action=str(arguments.get("action") or ""),
            objective=arguments.get("objective"),
            max_goal_rounds=arguments.get("max_goal_rounds"),
            blocked_reason=arguments.get("blocked_reason"),
        )
    except (ValueError, TypeError) as e:
        return _err(str(e))
    saved = store.set_session_goal(user_id, conv_id, updated)
    if saved is None:
        return _err("failed to save goal")
    return _ok(
        {
            "goal": saved["goal"],
            "ws_event": "agent.goal",
            "goal_event": str(arguments.get("action") or "update"),
        }
    )


def todo_write(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    try:
        todos = normalize_todos(arguments.get("todos"), allow_parallel_in_progress=False)
    except ValueError as e:
        return _err(str(e))
    saved = store.set_session_todos(user_id, conv_id, todos)
    if saved is None:
        return _err("conversation not found")
    counts = todo_counts(todos)
    return _ok(
        {
            "todos": todos,
            "counts": counts,
            "ws_event": "agent.todos",
            "todos_event": "write",
        }
    )


def todo_read(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    row = store.get_conversation_goal(user_id, conv_id)
    if row is None:
        return _err("conversation not found")
    todos = row.get("todos") if isinstance(row.get("todos"), list) else []
    return _ok({"todos": todos, "counts": todo_counts(todos), "ws_event": "agent.todos", "todos_event": "read"})


def plan_mode_set(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    active = arguments.get("active")
    if not isinstance(active, bool):
        return _err("active must be a boolean")
    saved = store.set_plan_mode(user_id, conv_id, active)
    if saved is None:
        return _err("conversation not found")
    return _ok(
        {
            "plan_mode": bool(saved.get("plan_mode")),
            "ws_event": "agent.plan_mode",
            "plan_event": "on" if active else "off",
        }
    )


def exit_plan_mode(arguments: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    req = _require_conversation(arguments, context)
    if isinstance(req, str):
        return _err(req)
    user_id, conv_id = req
    plan = str(arguments.get("plan") or "").strip()
    if not plan or "#" not in plan:
        return _err("plan must be markdown with at least one # heading")
    row = store.get_conversation_goal(user_id, conv_id)
    if row is None:
        return _err("conversation not found")
    if not row.get("plan_mode"):
        return _err("plan mode is not active")
    saved = store.set_plan_mode(user_id, conv_id, False)
    if saved is None:
        return _err("conversation not found")
    return _ok(
        {
            "plan_mode": False,
            "plan": plan[:12000],
            "ws_event": "agent.plan_mode",
            "plan_event": "exit",
        }
    )


HANDLERS = {
    "goal_get": goal_get,
    "goal_create": goal_create,
    "goal_update": goal_update,
    "todo_write": todo_write,
    "todo_read": todo_read,
    "plan_mode_set": plan_mode_set,
    "exit_plan_mode": exit_plan_mode,
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "goal_get",
            "description": "Get the current conversation ongoing goal (or null).",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goal_create",
            "description": (
                "Create one ongoing goal for this chat when the user asks for multi-step work. "
                "Not for single-turn Q&A. Not a product backlog task."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "Clear completion objective."},
                    "max_goal_rounds": {"type": "integer", "minimum": 1, "maximum": 500},
                },
                "required": ["objective"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goal_update",
            "description": (
                "Update the ongoing goal. Call goal_get first and pass exact goal_id + revision. "
                "Actions: edit, pause, resume, complete, blocked."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_id": {"type": "string"},
                    "revision": {"type": "integer", "minimum": 1},
                    "action": {
                        "type": "string",
                        "enum": ["edit", "pause", "resume", "complete", "blocked"],
                    },
                    "objective": {"type": "string"},
                    "max_goal_rounds": {"type": "integer", "minimum": 1, "maximum": 500},
                    "blocked_reason": {"type": "string"},
                },
                "required": ["goal_id", "revision", "action"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": (
                "Replace the session todo list for this chat run (whole list). "
                "Statuses: pending, in_progress, completed. At most one in_progress."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                            },
                            "required": ["content", "status"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["todos"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_read",
            "description": "Read the current session todo list for this chat.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_mode_set",
            "description": (
                "Turn soft plan mode on or off. When on, prefer planning over irreversible actions "
                "and finish with exit_plan_mode."
            ),
            "parameters": {
                "type": "object",
                "properties": {"active": {"type": "boolean"}},
                "required": ["active"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "exit_plan_mode",
            "description": (
                "Exit plan mode after presenting a markdown plan with at least one # heading."
            ),
            "parameters": {
                "type": "object",
                "properties": {"plan": {"type": "string"}},
                "required": ["plan"],
                "additionalProperties": False,
            },
        },
    },
]
