"""Shared project workspace value helpers."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from apps.backend.domain.workspace.location import (
    tenant_workspace_root,
    user_workspace_root,
    workspace_root_for,
)

AGENTLAYER_SELF_NAME = "agentlayer-self"
_WORKSPACE_NAME_MAX_LEN = 255
_CLIENT_PATH_MAX_LEN = 4096


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


def validate_client_workspace_path(raw: str | None) -> str:
    """Absolute path on the *client* machine. The backend must never open this string."""
    p = (raw or "").strip()
    if not p:
        raise WorkspaceCreateError("path is required for a client workspace")
    if len(p) > _CLIENT_PATH_MAX_LEN:
        raise WorkspaceCreateError(
            f"client workspace path must be at most {_CLIENT_PATH_MAX_LEN} characters"
        )
    if "\0" in p:
        raise WorkspaceCreateError("invalid path")
    posix = p.startswith("/")
    windows_drive = len(p) >= 3 and p[0].isalpha() and p[1] == ":" and p[2] in "/\\"
    windows_unc = p.startswith("\\\\")
    if not (posix or windows_drive or windows_unc):
        raise WorkspaceCreateError("client workspace path must be absolute")
    return p


def _contained_under(root: Path, name: str) -> Path:
    """Resolve ``name`` under ``root``, refusing anything that escapes it.

    The root is a parameter because there are two of them now. Hardcoding the
    user root here is what would put a tenant workspace outside its guard.
    """
    nm = validate_workspace_name(name)
    root_r = root.resolve()
    target = (root_r / nm).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        raise WorkspaceCreateError("invalid workspace name") from None
    return target


def resolve_user_workspace_dir(base: Path, user_id: Any, name: str) -> Path:
    return _contained_under(user_workspace_root(base, user_id), name)


def resolve_tenant_workspace_dir(base: Path, tenant_id: int, name: str) -> Path:
    return _contained_under(tenant_workspace_root(base, tenant_id), name)


def resolve_workspace_dir(
    base: Path,
    name: str,
    *,
    visibility: str,
    owner_user_id: Any,
    tenant_id: int | None,
) -> Path:
    """The create-time directory for a workspace, from the domain's placement rule."""
    root = workspace_root_for(
        base=base,
        visibility=visibility,
        owner_user_id=owner_user_id,
        tenant_id=tenant_id,
    )
    return _contained_under(root, name)


def workspace_base_path() -> Path:
    return Path(os.environ.get("AGENTLAYER_WORKSPACE_PATH", "/workspace"))


def slug_from_git_url(git_url: str) -> str:
    t = (git_url or "").strip().rstrip("/")
    if t.lower().endswith(".git"):
        t = t[:-4]
    seg = t.split("/")[-1] or "repo"
    seg = re.sub(r"[^a-zA-Z0-9_.-]+", "-", seg).strip("-_.")[:48]
    return seg or "repo"
