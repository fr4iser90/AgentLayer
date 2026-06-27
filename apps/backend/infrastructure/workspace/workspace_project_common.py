"""Shared project workspace value helpers."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

AGENTLAYER_SELF_NAME = "agentlayer-self"
_WORKSPACE_NAME_MAX_LEN = 255


class WorkspaceCreateError(Exception):
    """Raised when workspace creation cannot complete."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class WorkspaceState:
    """Workspace lifecycle states."""

    CREATED = "created"
    CLONING = "cloning"
    READY = "ready"
    ERROR = "error"


def validate_workspace_name(name: str) -> str:
    nm = (name or "").strip()
    if not nm:
        raise WorkspaceCreateError("name is required")
    if len(nm) > _WORKSPACE_NAME_MAX_LEN:
        raise WorkspaceCreateError(
            f"workspace name must be at most {_WORKSPACE_NAME_MAX_LEN} characters"
        )
    if nm in (".", ".."):
        raise WorkspaceCreateError("invalid workspace name")
    if "\0" in nm or "/" in nm or "\\" in nm:
        raise WorkspaceCreateError("workspace name must not contain path separators")
    return nm


def resolve_user_workspace_dir(base: Path, user_id: Any, name: str) -> Path:
    nm = validate_workspace_name(name)
    user_root = (base / str(user_id)).resolve()
    target = (user_root / nm).resolve()
    try:
        target.relative_to(user_root)
    except ValueError:
        raise WorkspaceCreateError("invalid workspace name") from None
    return target


def workspace_base_path() -> Path:
    return Path(os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace"))


def slug_from_git_url(git_url: str) -> str:
    t = (git_url or "").strip().rstrip("/")
    if t.lower().endswith(".git"):
        t = t[:-4]
    seg = t.split("/")[-1] or "repo"
    seg = re.sub(r"[^a-zA-Z0-9_.-]+", "-", seg).strip("-_.")[:48]
    return seg or "repo"
