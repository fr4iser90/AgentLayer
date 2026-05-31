"""Redirect ``coding_bash`` read/list/git-sync commands to dedicated ``coding_*`` tools."""

from __future__ import annotations

import re
import shlex
from typing import Any

_READLIKE_FIRST = frozenset({"cat", "head", "tail", "less", "more", "nl"})
_LISTLIKE_FIRST = frozenset({"ls", "dir"})
_PY_READ_OPEN = re.compile(
    r"""open\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.IGNORECASE,
)


def _strip_workspace_path(path: str, workspace_root: str | None) -> str:
    p = (path or "").strip().replace("\\", "/")
    if not p:
        return p
    root = (workspace_root or "").strip().replace("\\", "/").rstrip("/")
    if root and (p == root or p.startswith(root + "/")):
        p = p[len(root) :].lstrip("/")
    if p.startswith("/code/"):
        p = p[6:]
    elif p == "/code":
        p = "."
    elif p.startswith("/"):
        p = p.lstrip("/")
    return p


def _reject_readlike_bash(command: str) -> str:
    return (
        f"coding_bash is not for file reads/listing ({command[:100]!r}). "
        "Use coding_read_file, coding_list_dir, coding_search, or coding_glob instead."
    )


def redirect_coding_bash_command(
    command: str,
    *,
    workspace_root: str | None = None,
) -> tuple[str, dict[str, Any]] | str | None:
    """
    Map common shell read/list patterns to dedicated tools.

    Returns:
      - ``(tool_name, args)`` to execute instead of bash
      - ``str`` error when the command is read-like but not parseable
      - ``None`` when bash should run as-is (pytest, git diff, etc.)
    """
    cmd = (command or "").strip()
    if not cmd:
        return None
    try:
        parts = shlex.split(cmd)
    except ValueError:
        if any(x in cmd.lower() for x in ("cat ", "head ", "open(", "readlines")):
            return _reject_readlike_bash(cmd)
        return None
    if not parts:
        return None

    first = parts[0].lower()

    if first in ("python", "python3") and "-c" in parts:
        idx = parts.index("-c")
        if idx + 1 < len(parts):
            script = parts[idx + 1]
            m = _PY_READ_OPEN.search(script)
            if m:
                return "coding_read_file", {"path": _strip_workspace_path(m.group(1), workspace_root)}
        return _reject_readlike_bash(cmd)

    if "|" in cmd or ";" in cmd or "&&" in cmd or "||" in cmd:
        if first in _READLIKE_FIRST | _LISTLIKE_FIRST:
            return _reject_readlike_bash(cmd)
        return None

    if first in ("git",):
        sub = parts[1].lower() if len(parts) > 1 else ""
        if sub == "pull":
            return "coding_git_sync", {"operation": "pull"}
        if sub == "fetch":
            return "coding_git_sync", {"operation": "fetch"}
        return None

    if first in _LISTLIKE_FIRST:
        path = "."
        if len(parts) > 1 and not parts[1].startswith("-"):
            path = _strip_workspace_path(parts[1], workspace_root) or "."
        return "coding_list_dir", {"path": path}

    if first == "cat" and len(parts) == 2:
        return "coding_read_file", {"path": _strip_workspace_path(parts[1], workspace_root)}

    if first == "head":
        limit: int | None = None
        path: str | None = None
        i = 1
        while i < len(parts):
            tok = parts[i]
            if tok in ("-n", "--lines") and i + 1 < len(parts):
                try:
                    limit = max(1, int(parts[i + 1]))
                except ValueError:
                    return _reject_readlike_bash(cmd)
                i += 2
                continue
            if tok.startswith("-") and tok[1:].isdigit():
                limit = max(1, int(tok[1:]))
                i += 1
                continue
            if tok.startswith("-"):
                i += 1
                continue
            path = tok
            i += 1
        if path:
            out: dict[str, Any] = {"path": _strip_workspace_path(path, workspace_root)}
            if limit is not None:
                out["limit_lines"] = limit
            return "coding_read_file", out
        return _reject_readlike_bash(cmd)

    if first in _READLIKE_FIRST:
        return _reject_readlike_bash(cmd)

    # Absolute path in command without a dedicated tool — often model slop
    if re.search(r"/data/project_workspaces/", cmd) and first in ("cat", "head", "python3", "python"):
        return _reject_readlike_bash(cmd)

    return None
