"""Conversation goal + todos (scoped to one chat thread; not the product agent_tasks backlog)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any, Literal

GoalPhase = Literal["active", "paused", "completed", "blocked"]
TodoStatus = Literal["pending", "in_progress", "completed"]

VALID_GOAL_PHASES = frozenset({"active", "paused", "completed", "blocked"})
VALID_TODO_STATUSES = frozenset({"pending", "in_progress", "completed"})


def new_goal(*, objective: str, max_goal_rounds: int | None = None) -> dict[str, Any]:
    obj = (objective or "").strip()
    if not obj:
        raise ValueError("objective is required")
    rounds = 32
    if max_goal_rounds is not None:
        rounds = max(1, min(int(max_goal_rounds), 500))
    return {
        "id": str(uuid.uuid4()),
        "revision": 1,
        "objective": obj[:4000],
        "phase": "active",
        "rounds_started": 0,
        "max_goal_rounds": rounds,
        "blocked_reason": None,
    }


def apply_goal_update(
    current: dict[str, Any] | None,
    *,
    goal_id: str,
    revision: int,
    action: str,
    objective: str | None = None,
    max_goal_rounds: int | None = None,
    blocked_reason: str | None = None,
) -> dict[str, Any]:
    if not current:
        raise ValueError("no active goal")
    if str(current.get("id") or "") != str(goal_id).strip():
        raise ValueError("goal_id mismatch")
    if int(current.get("revision") or 0) != int(revision):
        raise ValueError("revision mismatch — call goal_get and retry")
    act = (action or "").strip().lower()
    out = dict(current)
    if act == "edit":
        if objective is not None and str(objective).strip():
            out["objective"] = str(objective).strip()[:4000]
        if max_goal_rounds is not None:
            out["max_goal_rounds"] = max(1, min(int(max_goal_rounds), 500))
        if out.get("phase") in ("completed", "blocked"):
            out["phase"] = "active"
            out["blocked_reason"] = None
    elif act == "pause":
        if out.get("phase") != "active":
            raise ValueError("only active goals can be paused")
        out["phase"] = "paused"
    elif act == "resume":
        if out.get("phase") not in ("paused", "blocked"):
            raise ValueError("only paused or blocked goals can be resumed")
        out["phase"] = "active"
        out["blocked_reason"] = None
    elif act == "complete":
        out["phase"] = "completed"
        out["blocked_reason"] = None
    elif act == "blocked":
        reason = (blocked_reason or "").strip()
        if not reason:
            raise ValueError("blocked_reason is required for action=blocked")
        out["phase"] = "blocked"
        out["blocked_reason"] = reason[:2000]
    elif act == "clear":
        raise ValueError("use clear via API/UI; tools use complete")
    else:
        raise ValueError("action must be edit|pause|resume|complete|blocked")
    out["revision"] = int(out.get("revision") or 1) + 1
    return out


def normalize_todos(raw: Any, *, allow_parallel_in_progress: bool = False) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("todos must be a list")
    if len(raw) > 40:
        raise ValueError("at most 40 todos")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    in_progress = 0
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each todo must be an object")
        content = str(item.get("content") or "").strip()
        if not content:
            raise ValueError("todo content is required")
        if len(content) > 500:
            raise ValueError("todo content too long")
        key = content.lower()
        if key in seen:
            raise ValueError(f"duplicate todo content: {content}")
        seen.add(key)
        status = str(item.get("status") or "pending").strip().lower()
        if status not in VALID_TODO_STATUSES:
            raise ValueError("todo status must be pending|in_progress|completed")
        if status == "in_progress":
            in_progress += 1
        out.append({"content": content, "status": status})
    if not allow_parallel_in_progress and in_progress > 1:
        raise ValueError("at most one todo may be in_progress")
    return out


def todo_counts(todos: list[dict[str, Any]] | None) -> dict[str, int]:
    pending = in_progress = completed = 0
    for item in todos or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip().lower()
        if status == "pending":
            pending += 1
        elif status == "in_progress":
            in_progress += 1
        elif status == "completed":
            completed += 1
    return {"pending": pending, "in_progress": in_progress, "completed": completed}


PLAN_MODE_GUIDANCE = (
    "Plan mode is active. Think through the approach first: outline steps, risks, and open questions. "
    "Prefer reading and planning over irreversible actions. When the plan is ready for the user, "
    "call exit_plan_mode with a clear markdown plan (include at least one # heading). "
    "Do not leave plan mode silently."
)


GOAL_TOOLS = frozenset({"goal_get", "goal_create", "goal_update"})
TODO_TOOLS = frozenset({"todo_write", "todo_read"})
PLAN_TOOLS = frozenset({"plan_mode_set", "exit_plan_mode"})

_TODO_MARKERS = {"completed": "x", "in_progress": ">", "pending": " "}


def _render_todo_lines(todos: list[dict[str, Any]] | None) -> list[str]:
    out: list[str] = []
    for item in todos or []:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        status = str(item.get("status") or "pending").strip().lower()
        out.append(f"- [{_TODO_MARKERS.get(status, ' ')}] {content}")
    return out


def _goal_section(goal: dict[str, Any] | None) -> list[str]:
    phase = str(goal.get("phase") or "").strip().lower() if isinstance(goal, dict) else ""
    if not isinstance(goal, dict) or phase not in ("active", "paused", "blocked"):
        return [
            "No ongoing goal. If this request needs several rounds of work, call `goal_create` once "
            "with a clear completion objective. Do not create a goal for a single answer or one lookup.",
        ]
    objective = str(goal.get("objective") or "").strip() or "(no objective)"
    round_no = int(goal.get("rounds_started") or 0)
    max_rounds = int(goal.get("max_goal_rounds") or 32)
    lines = [
        f"Ongoing goal ({phase}, round {round_no}/{max_rounds}): {objective}",
        f"To change it pass `goal_id={goal.get('id')}` and `revision={goal.get('revision')}` to `goal_update` "
        "— on a revision mismatch call `goal_get` and retry.",
    ]
    if phase == "active":
        lines.append(
            "Keep working toward this objective. Use `goal_update` with action `complete` once it is met, "
            "or `blocked` with a reason if you cannot proceed. Do not invent a second goal."
        )
    elif phase == "blocked":
        reason = str(goal.get("blocked_reason") or "").strip()
        lines.append(
            f"The goal is blocked{f' ({reason})' if reason else ''}. Resolve the blocker and `resume`, "
            "or tell the user what you need."
        )
    else:
        lines.append("The goal is paused — do not continue it until the user resumes.")
    return lines


def _todo_section(todos: list[dict[str, Any]] | None) -> list[str]:
    lines = _render_todo_lines(todos)
    if not lines:
        return [
            "No session todos. For work with three or more distinct steps, call `todo_write` with the "
            "full list before you start, then keep it updated as you go.",
        ]
    return [
        "Session todos (`[x]` done, `[>]` in progress):",
        *lines,
        "Send the whole list on every `todo_write`; keep exactly one item `in_progress` and mark items "
        "`completed` as soon as they are done.",
    ]


def conversation_goal_prompt_block(
    *,
    tool_names: Iterable[str],
    goal: dict[str, Any] | None = None,
    todos: list[dict[str, Any]] | None = None,
    plan_mode: bool = False,
) -> str:
    """System block describing the goal/todo tools the agent has plus their current state.

    Returns ``""`` when the agent has none of those tools, so callers can inject blindly.
    """
    available = {str(n).strip() for n in tool_names if str(n).strip()}
    sections: list[list[str]] = []
    if available & GOAL_TOOLS:
        sections.append(_goal_section(goal))
    if available & TODO_TOOLS:
        sections.append(_todo_section(todos))
    if plan_mode and available & PLAN_TOOLS:
        sections.append([PLAN_MODE_GUIDANCE])
    if not sections:
        return ""
    body = "\n\n".join("\n".join(section) for section in sections)
    return f"## Conversation goal & todos (this chat only — not the product task backlog)\n\n{body}"


def goal_round_prompt(*, objective: str, round_no: int, max_rounds: int, todos_summary: str) -> str:
    obj = (objective or "").strip() or "(no objective)"
    todos = (todos_summary or "").strip() or "(no session todos)"
    return (
        f"[Goal round {round_no}/{max_rounds}] Continue the ongoing goal without waiting for a new user message.\n"
        f"Objective: {obj}\n"
        f"Session todos: {todos}\n"
        "Update todos as you progress. Call goal_update to pause, complete, or mark blocked when appropriate. "
        "Do not invent a new goal."
    )
