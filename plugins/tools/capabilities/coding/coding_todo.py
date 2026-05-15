"""Todo list management for the current coding session."""

from __future__ import annotations

import json
from typing import Any, Callable

__version__ = "1.0.0"
TOOL_ID = "coding_todo"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding todo", "todo", "task list")
TOOL_CAPABILITIES = ("coding.meta",)
TOOL_LABEL = "Coding: Todo"
TOOL_DESCRIPTION = (
    "Create, update, and track a todo list for the current coding session. "
    "Each todo has content, status (pending/in_progress/completed/cancelled), and priority (high/medium/low). "
    "Call with the full updated todo list — the tool replaces the entire list."
)

_valid_statuses = frozenset({"pending", "in_progress", "completed", "cancelled"})
_valid_priorities = frozenset({"high", "medium", "low"})

_session_todos: list[dict[str, str]] = []


def _validate_item(item: dict[str, Any], idx: int) -> str | None:
    content = item.get("content")
    if not content or not str(content).strip():
        return f"todo[{idx}]: content is required and must be non-empty"
    status = str(item.get("status", "pending")).strip().lower()
    if status not in _valid_statuses:
        return f"todo[{idx}]: status must be one of {sorted(_valid_statuses)}, got {status!r}"
    priority = str(item.get("priority", "medium")).strip().lower()
    if priority not in _valid_priorities:
        return f"todo[{idx}]: priority must be one of {sorted(_valid_priorities)}, got {priority!r}"
    return None


def coding_todo(arguments: dict[str, Any]) -> str:
    global _session_todos
    todos_raw = arguments.get("todos")
    if todos_raw is None:
        return json.dumps(
            {
                "ok": True,
                "todos": _session_todos,
                "detail": "No todos argument provided — returning current list. To update, pass {\"todos\": [...]}.",
            },
            ensure_ascii=False,
        )
    if not isinstance(todos_raw, list):
        return json.dumps({"ok": False, "error": "todos must be a list of objects"}, ensure_ascii=False)
    for idx, item in enumerate(todos_raw):
        if not isinstance(item, dict):
            return json.dumps({"ok": False, "error": f"todos[{idx}] must be an object"}, ensure_ascii=False)
        err = _validate_item(item, idx)
        if err:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
    _session_todos = [
        {
            "content": str(item["content"]).strip(),
            "status": str(item.get("status", "pending")).strip().lower(),
            "priority": str(item.get("priority", "medium")).strip().lower(),
        }
        for item in todos_raw
    ]
    remaining = sum(1 for t in _session_todos if t["status"] != "completed")
    return json.dumps(
        {
            "ok": True,
            "todos": _session_todos,
            "remaining": remaining,
            "total": len(_session_todos),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_todo": coding_todo,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_todo",
            "TOOL_DESCRIPTION": "Create, update, and track a todo list for the current coding session. "
            "Each todo has content, status (pending/in_progress/completed/cancelled), and priority (high/medium/low). "
            "Call with the full updated todo list — the tool replaces the entire list.",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "TOOL_DESCRIPTION": "Brief description of the task",
                                },
                                "status": {
                                    "type": "string",
                                    "TOOL_DESCRIPTION": "pending, in_progress, completed, or cancelled",
                                },
                                "priority": {
                                    "type": "string",
                                    "TOOL_DESCRIPTION": "high, medium, or low",
                                },
                            },
                            "required": ["content"],
                        },
                        "TOOL_DESCRIPTION": "The complete updated todo list",
                    },
                },
            },
        },
    },
]
