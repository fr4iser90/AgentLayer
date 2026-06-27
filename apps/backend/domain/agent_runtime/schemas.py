"""Agent runtime schema validation."""
from __future__ import annotations


def validate_agent_run_status(status: str) -> str:
    value = status.strip().lower()
    if value not in {"queued", "running", "waiting", "succeeded", "failed", "cancelled"}:
        raise ValueError("invalid agent run status")
    return value


def validate_agent_turn_role(role: str) -> str:
    value = role.strip().lower()
    if value not in {"user", "assistant", "tool", "system"}:
        raise ValueError("invalid agent turn role")
    return value
