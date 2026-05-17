"""Collect tool events during a scheduled coding run (ContextVar, read by agent loop)."""

from __future__ import annotations

import uuid
from contextvars import ContextVar, Token
from typing import Any

_schedule_run_id: ContextVar[uuid.UUID | None] = ContextVar("schedule_run_id", default=None)
_schedule_tool_events: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "schedule_tool_events", default=None
)
_schedule_abort_reason: ContextVar[str | None] = ContextVar("schedule_abort_reason", default=None)


def begin_schedule_run_collection(run_id: uuid.UUID) -> tuple[Token, Token]:
    """Start collecting tool invocations for ``run_id``."""
    t1 = _schedule_run_id.set(run_id)
    t2 = _schedule_tool_events.set([])
    _schedule_abort_reason.set(None)
    return t1, t2


def record_schedule_abort(reason: str) -> None:
    if _schedule_run_id.get() is not None and reason.strip():
        _schedule_abort_reason.set(reason.strip()[:200])


def get_schedule_abort_reason() -> str | None:
    return _schedule_abort_reason.get()


def reset_schedule_run_collection(t1: Token, t2: Token) -> None:
    _schedule_run_id.reset(t1)
    _schedule_tool_events.reset(t2)


def get_schedule_tool_events() -> list[dict[str, Any]]:
    ev = _schedule_tool_events.get()
    return list(ev) if ev else []


def _truncate_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > 400:
            out[k] = f"{v[:400]}… <{len(v)} chars>"
        else:
            out[k] = v
    return out


def record_schedule_tool_event(
    *,
    round_num: int,
    tool_name: str,
    args: dict[str, Any],
    ok: bool,
    error: str | None = None,
) -> None:
    if _schedule_run_id.get() is None:
        return
    events = _schedule_tool_events.get()
    if events is None:
        return
    events.append(
        {
            "round": round_num,
            "name": tool_name,
            "ok": ok,
            "args": _truncate_args(args),
            **({"error": (error or "")[:500]} if error else {}),
        }
    )
