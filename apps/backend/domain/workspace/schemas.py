"""Workspace schema validation."""
from __future__ import annotations


def validate_workspace_path(path: str | None) -> str | None:
    if path is None:
        return None
    value = path.strip()
    if not value:
        raise ValueError("workspace path must not be blank")
    if "\x00" in value:
        raise ValueError("workspace path contains invalid NUL byte")
    return value


def validate_verify_command(command: str | None) -> str | None:
    value = (command or "").strip()
    if not value:
        return None
    if len(value) > 4000:
        raise ValueError("verify command is too long")
    return value
