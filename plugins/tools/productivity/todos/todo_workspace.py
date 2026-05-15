"""Agent tools for ``kind: todo`` dashboards — checkbox tasks, optional due hints, notes (see ``dashboard/tasks``)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import (
    resolve_dashboard_id_for_kind,
    dashboard_rows_for_kind,
)

__version__ = "1.0.0"
TOOL_ID = "todo"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "tasks"
TOOL_LABEL = "Task list"
TOOL_DESCRIPTION = (
    "Read and update task-list dashboards (kind todo): checkbox tasks (title, optional due text), "
    "and markdown notes. This is the correct tool for todos / tasks / checklists — not ideas or shopping. "
    "dashboard_id is optional when the user has exactly one todo board; if several exist, call "
    "todo_dashboards or pass dashboard_id. Prefer [Dashboard context] when present."
)
TOOL_TRIGGERS = (
    "todo",
    "todos",
    "to-do",
    "to do",
    "task list",
    "tasklist",
    "checklist",
    "aufgabe",
    "aufgaben",
    "erledigt",
    "fällig",
)
TOOL_CAPABILITIES = ("dashboard.todo.read", "dashboard.todo.write")

_MAX_TASKS = 500
_MAX_BATCH = 40
_MAX_TITLE = 500
_MAX_DUE = 120


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _ensure_todo(ws: dict[str, Any]) -> str | None:
    if (ws.get("kind") or "").strip() != "todo":
        return "dashboard is not a todo (task list) kind"
    return None


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) > max_len:
        return t[:max_len]
    return t


def _normalize_task(entry: dict[str, Any]) -> dict[str, Any] | None:
    title = (entry.get("title") or entry.get("name") or "").strip()
    if not title:
        return None
    title = _clip(title, _MAX_TITLE)
    due_raw = entry.get("due")
    due = _clip(str(due_raw), _MAX_DUE) if due_raw is not None and str(due_raw).strip() else ""
    done = bool(entry.get("done", False))
    return {
        "id": str(uuid.uuid4()),
        "done": done,
        "title": title,
        "due": due,
    }


def _coerce_task_list(arguments: dict[str, Any]) -> list[Any] | None:
    """
    Models often send ``rows`` (ideas/shopping shape) or a JSON string instead of ``tasks``.
    """
    raw: Any = arguments.get("tasks")
    if raw is None or (isinstance(raw, list) and not raw):
        raw = arguments.get("rows")
    if isinstance(raw, str):
        t = raw.strip()
        if not t:
            return None
        try:
            parsed: Any = json.loads(t)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            if isinstance(parsed.get("tasks"), list):
                return parsed["tasks"]
            if isinstance(parsed.get("rows"), list):
                return parsed["rows"]
        return None
    if isinstance(raw, list):
        return raw
    return None


def todo_dashboards(arguments: dict[str, Any]) -> str:
    """List todo (task list) dashboards for the current user."""
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — todo tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "todo")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def todo_read(arguments: dict[str, Any]) -> str:
    """Return tasks and notes for one todo dashboard."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — todo tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="todo", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_todo(ws)
    if bad:
        return _err(bad)

    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        tasks = []
    notes = data.get("notes")
    if not isinstance(notes, str):
        notes = ""

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "title": ws.get("title") or "",
            "tasks": tasks,
            "notes": notes,
        },
        ensure_ascii=False,
    )


def todo_add_tasks(arguments: dict[str, Any]) -> str:
    """Append tasks to a todo dashboard."""
    raw = _coerce_task_list(arguments)
    if not raw:
        return _err(
            "tasks must be a non-empty array of {title, due?, done?} — "
            "use key tasks (rows is accepted as alias); strings must be JSON arrays."
        )

    ident = _identity()
    if ident is None:
        return _err("No user identity — todo tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="todo", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_todo(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur = data.get("tasks")
    if not isinstance(cur, list):
        cur = []
    if len(cur) >= _MAX_TASKS:
        return _err(f"list already has max {_MAX_TASKS} tasks — remove rows in the UI first")

    new_rows: list[dict[str, Any]] = []
    for entry in raw[:_MAX_BATCH]:
        if not isinstance(entry, dict):
            continue
        row = _normalize_task(entry)
        if row:
            new_rows.append(row)
    if not new_rows:
        return _err("no valid tasks — each needs a non-empty title")

    if len(cur) + len(new_rows) > _MAX_TASKS:
        return _err(f"would exceed {_MAX_TASKS} tasks — add fewer tasks first")

    merged = list(cur) + new_rows
    data["tasks"] = merged
    if "notes" not in data:
        data["notes"] = ""

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "added": len(new_rows),
            "tasks_count": len(merged),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "todo_dashboards": todo_dashboards,
    "todo_read": todo_read,
    "todo_add_tasks": todo_add_tasks,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "todo_dashboards",
            "TOOL_DESCRIPTION": (
                "List task-list dashboards (kind todo). Call when which board is unclear and "
                "there is no [Dashboard context] dashboard_id, or the user may mean a list other than the default."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_read",
            "TOOL_DESCRIPTION": (
                "Read tasks and markdown notes for one todo (task list) dashboard. "
                "Omit dashboard_id when the user has exactly one todo board; else pass UUID or list dashboards."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single todo dashboard).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todo_add_tasks",
            "TOOL_DESCRIPTION": (
                "Add one or more tasks (title required; optional due text, optional done). "
                "Pass a JSON array in tasks=[...]. Do not output JSON in chat — call this tool. "
                "If you mistakenly use rows= like ideas/shopping, that is accepted as alias. "
                "Use for todos / task lists — not shopping or ideas dashboards. "
                "Omit dashboard_id when the user has exactly one todo dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single todo dashboard).",
                    },
                    "tasks": {
                        "type": "array",
                        "TOOL_DESCRIPTION": "Objects with title (or name), optional due, optional done",
                        "items": {"type": "object"},
                    },
                    "rows": {
                        "type": "array",
                        "TOOL_DESCRIPTION": "Alias for tasks (same shape) if the model uses ideas-style key.",
                        "items": {"type": "object"},
                    },
                },
                "required": [],
            },
        },
    },
]
