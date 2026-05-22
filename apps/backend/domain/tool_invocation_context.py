"""Per-request chat messages visible to tool handlers (set only around :func:`run_tool` from the agent loop)."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any

_tool_invocation_messages: ContextVar[list[dict[str, Any]] | None] = ContextVar(
    "tool_invocation_messages", default=None
)

_capability_confirmed: ContextVar[frozenset[str]] = ContextVar(
    "agent_capability_confirmed", default=frozenset()
)

_agent_run_id: ContextVar[str | None] = ContextVar("agent_layer_run_id", default=None)
_agent_task_id: ContextVar[str | None] = ContextVar("agent_layer_task_id", default=None)


def get_agent_run_id() -> str | None:
    return _agent_run_id.get()


def set_agent_run_id(run_id: str | None) -> Token[str | None]:
    return _agent_run_id.set(run_id)


def reset_agent_run_id(token: Token[str | None]) -> None:
    _agent_run_id.reset(token)


def get_agent_task_id() -> str | None:
    return _agent_task_id.get()


def set_agent_task_id(task_id: str | None) -> Token[str | None]:
    return _agent_task_id.set(task_id)


def reset_agent_task_id(token: Token[str | None]) -> None:
    _agent_task_id.reset(token)


def get_tool_invocation_messages() -> list[dict[str, Any]] | None:
    return _tool_invocation_messages.get()


def set_tool_invocation_messages(messages: list[dict[str, Any]]) -> Token[list[dict[str, Any]] | None]:
    """Shallow copy recommended; handlers must treat messages as read-only."""
    return _tool_invocation_messages.set(messages)


def reset_tool_invocation_messages(token: Token[list[dict[str, Any]] | None]) -> None:
    _tool_invocation_messages.reset(token)


def bind_capability_confirmed(caps: frozenset[str]) -> Token[frozenset[str]]:
    """Set confirmed capability ids for :func:`capability_governance.capability_gate_error_json`."""
    return _capability_confirmed.set(caps)


def reset_capability_confirmed(token: Token[frozenset[str]]) -> None:
    _capability_confirmed.reset(token)


def get_capability_confirmed() -> frozenset[str]:
    return _capability_confirmed.get()
