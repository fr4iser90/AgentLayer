"""Git push in the coding workspace using per-user ``github_pat`` (no shell)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.github.auth import (
    USER_SECRET_KEY,
    askpass_extra_env,
    cleanup_askpass_paths,
    git_auth_failure_reason,
    github_pat_for_current_user,
    no_github_pat_payload,
    redact_secrets,
)
from plugins.tools.integrations.github.git_read import _git_ok, _tail

__version__ = "1.0.0"
TOOL_ID = "git_push"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "github"
TOOL_TRIGGERS = (
    "git push",
    "push branch",
    "publish branch",
    "push to github",
    "upload branch",
)
TOOL_CAPABILITIES = ("coding.execute",)
TOOL_SECRETS_REQUIRED = (USER_SECRET_KEY,)
TOOL_LABEL = "Coding: Git push"
TOOL_DESCRIPTION = (
    "Push the current branch (or a named branch) to a remote via ``git -C <workspace> push``. "
    "Uses the signed-in user's ``github_pat`` from Settings → Connections (not shell, not .env). "
    "Do not use ``bash`` for push."
)

MAX_OUTPUT_BYTES = 80_000
DEFAULT_TIMEOUT = 120


def _current_branch(root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root.resolve()), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    ref = (proc.stdout or "").strip()
    return ref or None


def _run_git_push(
    root: Path,
    args: list[str],
    *,
    timeout: int,
    extra_env: dict[str, str],
) -> tuple[int, str]:
    cmd = ["git", "-C", str(root.resolve()), "push", *args]
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **extra_env}
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


def git_push(arguments: dict[str, Any], context: dict | None = None) -> str:
    from apps.backend.domain.coding.common import (
        json_workspace_missing_error,
        workspace_binding_from_context,
    )

    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()

    token = github_pat_for_current_user()
    if not token:
        return json.dumps(no_github_pat_payload(), ensure_ascii=False)

    root = Path(ws["path"]).resolve()
    ok, err = _git_ok(root)
    if not ok:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)

    remote = str(arguments.get("remote") or "origin").strip() or "origin"
    branch = str(arguments.get("branch") or "").strip()
    if not branch:
        branch = _current_branch(root) or ""
    if not branch:
        return json.dumps(
            {"ok": False, "error": "could not determine branch; pass branch explicitly"},
            ensure_ascii=False,
        )

    set_upstream = arguments.get("set_upstream")
    if set_upstream is None:
        do_upstream = True
    elif isinstance(set_upstream, bool):
        do_upstream = set_upstream
    else:
        do_upstream = str(set_upstream).strip().lower() in ("1", "true", "yes", "on")

    try:
        timeout_s = max(15, min(int(arguments.get("timeout", DEFAULT_TIMEOUT)), 600))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT

    push_args: list[str] = []
    if do_upstream:
        push_args.extend(["-u", remote, branch])
    else:
        push_args.extend([remote, branch])

    extra_env, cleanup_paths = askpass_extra_env(token)
    code = -1
    out = ""
    try:
        code, out = _run_git_push(root, push_args, timeout=timeout_s, extra_env=extra_env)
    finally:
        cleanup_askpass_paths(cleanup_paths)

    safe_out = redact_secrets(out, token)
    preview, cut = _tail(safe_out, MAX_OUTPUT_BYTES)
    payload: dict[str, Any] = {
        "ok": code == 0,
        "remote": remote,
        "branch": branch,
        "set_upstream": do_upstream,
        "exit_code": code,
        "output": preview,
        "truncated": cut,
        "github_auth": "pat_injected",
        "message": "Push completed." if code == 0 else "Push failed.",
    }
    reason = git_auth_failure_reason(safe_out, code)
    if reason:
        payload["reason"] = reason
    if reason == "auth_denied":
        payload["error"] = (
            "GitHub rejected credentials (check github_pat scopes, expiry, SSO, "
            "and that origin uses https://github.com/… not git@github.com)."
        )
    elif code != 0 and "error" not in payload:
        payload["error"] = preview[:500] if preview else f"push failed (exit {code})"
    return json.dumps(payload, ensure_ascii=False)


HANDLERS: dict[str, Callable[..., str]] = {
    "git_push": git_push,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "remote": {
                        "type": "string",
                        "description": "Remote name (default origin)",
                    },
                    "branch": {
                        "type": "string",
                        "description": "Branch to push (default: current HEAD)",
                    },
                    "set_upstream": {
                        "type": "boolean",
                        "description": "Pass -u to set upstream (default true)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout seconds (15–600, default 120)",
                    },
                },
            },
        },
    },
]
