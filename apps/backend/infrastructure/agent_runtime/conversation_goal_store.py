"""Persist per-conversation goal / todos / plan mode (not the product agent_tasks backlog)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from psycopg.types.json import Json

from apps.backend.infrastructure.db import db


def _parse_json(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return default
    return default


def _pack(goal: Any, todos: Any, plan_mode: Any = False) -> dict[str, Any]:
    g = goal if isinstance(goal, dict) else None
    t = todos if isinstance(todos, list) else []
    return {"goal": g, "todos": t, "plan_mode": bool(plan_mode)}


def get_conversation_goal(user_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    """Return ``{goal, todos, plan_mode}`` if the user may access the conversation."""
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, shared, session_goal, session_todos, session_plan_mode
                FROM chat_conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            row_user, shared = row[0], bool(row[1])
            if shared:
                return None
            if row_user != user_id:
                return None
            goal = _parse_json(row[2], None)
            todos = _parse_json(row[3], [])
            plan_mode = bool(row[4]) if len(row) > 4 else False
            return _pack(goal, todos, plan_mode)


def set_session_goal(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    goal: dict[str, Any] | None,
) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_conversations
                SET session_goal = %s::jsonb, updated_at = now()
                WHERE id = %s AND user_id = %s AND shared = false
                RETURNING session_goal, session_todos, session_plan_mode
                """,
                (Json(goal) if goal is not None else None, conversation_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
        conn.commit()
    return _pack(_parse_json(row[0], None), _parse_json(row[1], []), row[2] if len(row) > 2 else False)


def set_session_todos(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    todos: list[dict[str, Any]],
) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_conversations
                SET session_todos = %s::jsonb, updated_at = now()
                WHERE id = %s AND user_id = %s AND shared = false
                RETURNING session_goal, session_todos, session_plan_mode
                """,
                (Json(todos), conversation_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
        conn.commit()
    return _pack(_parse_json(row[0], None), _parse_json(row[1], []), row[2] if len(row) > 2 else False)


def set_plan_mode(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    active: bool,
) -> dict[str, Any] | None:
    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_conversations
                SET session_plan_mode = %s, updated_at = now()
                WHERE id = %s AND user_id = %s AND shared = false
                RETURNING session_goal, session_todos, session_plan_mode
                """,
                (bool(active), conversation_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
        conn.commit()
    return _pack(_parse_json(row[0], None), _parse_json(row[1], []), row[2])


def bump_goal_round(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> dict[str, Any] | None:
    """Increment ``rounds_started`` on the active goal; return the updated row or None."""
    row = get_conversation_goal(user_id, conversation_id)
    if row is None:
        return None
    goal = row.get("goal")
    if not isinstance(goal, dict) or str(goal.get("phase") or "") != "active":
        return row
    g = dict(goal)
    started = int(g.get("rounds_started") or 0) + 1
    g["rounds_started"] = started
    g["revision"] = int(g.get("revision") or 1) + 1
    return set_session_goal(user_id, conversation_id, g)
