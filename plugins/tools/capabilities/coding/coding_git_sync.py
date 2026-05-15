"""Git fetch/pull in the coding workspace (mutating; non-interactive ``git -C``)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from plugins.tools.capabilities.coding.coding_git_read import _git_ok, _tail

__version__ = "1.0.0"
TOOL_ID = "coding_git_sync"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = (
    "git pull",
    "git fetch",
    "pull latest",
    "update repo",
    "repository aktualisieren",
    "workspace updaten",
)
TOOL_CAPABILITIES = ("coding.execute",)
TOOL_LABEL = "Coding: Git sync"
TOOL_DESCRIPTION = (
    "Run **git fetch** or **git pull** in the workspace root via ``git -C <workspace>`` (no shell). "
    "Default **pull** uses ``--ff-only --no-edit`` (fast-forward only; fails if a merge commit is required). "
    "Use **fetch** to download remote refs without merging. "
    "Requires a normal ``.git`` checkout at the workspace root."
)

MAX_OUTPUT_BYTES = 80_000
DEFAULT_TIMEOUT = 120
FETCH_TIMEOUT = 90


def _run_git(
    root: Path,
    args: list[str],
    *,
    timeout: int,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str]:
    cmd = ["git", "-C", str(root.resolve()), *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, str(e)
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out


def coding_git_sync(arguments: dict[str, Any], context: dict | None = None) -> str:
    from plugins.tools.capabilities.coding.coding_common import (
        json_workspace_missing_error,
        workspace_binding_from_context,
    )

    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"]).resolve()
    ok, err = _git_ok(root)
    if not ok:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)

    op = str(arguments.get("operation") or "pull").strip().lower()
    if op not in ("pull", "fetch"):
        return json.dumps(
            {"ok": False, "error": "operation must be 'pull' or 'fetch'"},
            ensure_ascii=False,
        )

    try:
        timeout_s = max(15, min(int(arguments.get("timeout", DEFAULT_TIMEOUT)), 600))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT if op == "pull" else FETCH_TIMEOUT

    remote = str(arguments.get("remote") or "origin").strip() or "origin"
    branch = str(arguments.get("branch") or "").strip()

    if op == "fetch":
        t = min(timeout_s, FETCH_TIMEOUT)
        code, out = _run_git(root, ["fetch", "--prune", remote], timeout=t)
    else:
        cmd = ["pull", "--ff-only", "--no-edit"]
        if branch:
            cmd.extend([remote, branch])
        elif remote != "origin":
            cmd.append(remote)
        code, out = _run_git(root, cmd, timeout=timeout_s)

    preview, cut = _tail(out, MAX_OUTPUT_BYTES)
    return json.dumps(
        {
            "ok": code == 0,
            "operation": op,
            "exit_code": code,
            "output": preview,
            "truncated": cut,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[..., str]] = {
    "coding_git_sync": coding_git_sync,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_git_sync",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "pull (default, fast-forward only) or fetch",
                    },
                    "remote": {
                        "type": "string",
                        "description": "Remote name (default origin)",
                    },
                    "branch": {
                        "type": "string",
                        "description": "For pull only: optional explicit branch to merge from remote",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout seconds (15–600, default 120 for pull)",
                    },
                },
            },
        },
    },
]
