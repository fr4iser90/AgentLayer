"""Delegation schema validation."""
from __future__ import annotations


def validate_delegation_instruction(instruction: str) -> str:
    value = instruction.strip()
    if not value:
        raise ValueError("delegation instruction must not be blank")
    return value


def validate_delegation_status(status: str) -> str:
    value = status.strip().lower()
    if value not in {"requested", "running", "succeeded", "failed", "cancelled"}:
        raise ValueError("invalid delegation status")
    return value
