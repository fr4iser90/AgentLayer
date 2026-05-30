"""Execute shell commands within the coding root directory."""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from plugins.tools.capabilities.coding.coding_bash_policy import (
    coding_bash_strict_enabled,
    is_blocked,
    resolve_path_under_workspace,
    strict_mode_reject_reason,
    subprocess_env_for_coding,
)
from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)
from plugins.tools.capabilities.coding.coding_git_auth import (
    askpass_extra_env,
    cleanup_askpass_paths,
    git_auth_failure_reason,
    git_command_needs_github_pat,
    github_pat_for_current_user,
    no_github_pat_payload,
    redact_secrets,
)

__version__ = "1.0.0"
TOOL_ID = "coding_bash"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = (
    "coding bash",
    "run command",
    "shell",
    "execute",
    "git clone",
    "git pull",
    "git checkout",
    "repository",
    "repo",
    "github.com",
    "gitlab",
    "clone",
)
TOOL_CAPABILITIES = ("coding.execute",)
TOOL_LABEL = "Coding: Bash"
TOOL_DESCRIPTION = (
    "Run a shell command within the coding workspace. "
    "Output is truncated if too large; use workdir to set the directory. "
    "Supports timeout. Dangerous commands (rm -rf /, curl|sh, git clean -fdx, etc.) are blocked."
)

DEFAULT_TIMEOUT = 120
MAX_OUTPUT_BYTES = 50_000


def _classify_git_pull_output(out: str, exit_code: int) -> str:
    if exit_code != 0:
        return "failed"
    low = (out or "").lower()
    if "already up to date" in low or "already up-to-date" in low:
        return "already_up_to_date"
    if "fast-forward" in low or "updating" in low:
        return "fast_forward"
    return "completed"


def _tail(text: str, max_bytes: int, max_lines: int = 200) -> tuple[str, bool]:
    lines = text.split("\n")
    if len(lines) <= max_lines and len(text.encode("utf-8")) <= max_bytes:
        return text, False
    out: list[str] = []
    total_bytes = 0
    for line in reversed(lines):
        line_bytes = len(line.encode("utf-8"))
        if total_bytes + line_bytes > max_bytes or len(out) >= max_lines:
            break
        out.append(line)
        total_bytes += line_bytes
    out.reverse()
    return "\n".join(out), True


def coding_bash(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])

    command = (arguments.get("command") or "").strip()
    if not command:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "coding_bash requires a non-empty string field \"command\" (the shell command to run). "
                    'Example arguments: {"command": "git status"} or '
                    '{"command": "git clone https://github.com/org/repo.git .", "timeout": 120}'
                ),
            },
            ensure_ascii=False,
        )
    blocked = is_blocked(command)
    if blocked:
        return json.dumps({"ok": False, "error": blocked}, ensure_ascii=False)
    if coding_bash_strict_enabled():
        strict_err = strict_mode_reject_reason(command)
        if strict_err:
            return json.dumps({"ok": False, "error": strict_err}, ensure_ascii=False)

    workdir_rel = (arguments.get("workdir") or "").strip()
    try:
        cwd = resolve_path_under_workspace(root, workdir_rel or None)
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    try:
        timeout_s = max(1, int(arguments.get("timeout", DEFAULT_TIMEOUT)))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT

    needs_pat = git_command_needs_github_pat(command)
    pat_token: str | None = None
    askpass_cleanup: list[str] = []
    extra_env: dict[str, str] = {}
    if needs_pat:
        pat_token = github_pat_for_current_user()
        if not pat_token:
            return json.dumps(no_github_pat_payload(), ensure_ascii=False)
        extra_env, askpass_cleanup = askpass_extra_env(pat_token)

    env = subprocess_env_for_coding(home=str(root.resolve()), cwd=cwd, extra=extra_env)

    try:
        # Split command into argument list and run without shell to prevent command injection.
        # The blocklist (is_blocked) above already rejects dangerous shell operators (|, &&, ||,
        # backticks, $(), etc.), so shell=False is safe here.
        args = shlex.split(command)
        result = subprocess.run(
            args,
            shell=False,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        out_text = ""
        if e.stdout:
            out_text += str(e.stdout)
        if e.stderr:
            out_text += "\n" + str(e.stderr)
        out_text = redact_secrets(out_text, pat_token)
        preview, cut = _tail(out_text, MAX_OUTPUT_BYTES)
        detail = "..." if cut else ""
        return json.dumps(
            {
                "ok": False,
                "error": f"command timed out after {timeout_s}s",
                "exit_code": -1,
                "truncated": cut,
                "output": f"{detail}{preview}",
            },
            ensure_ascii=False,
        )
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    finally:
        if askpass_cleanup:
            cleanup_askpass_paths(askpass_cleanup)
    combined = ""
    if result.stdout:
        combined += result.stdout
    if result.stderr:
        if combined:
            combined += "\n--- stderr ---\n"
        combined += result.stderr
    if not combined:
        combined = "(no output)"
    combined = redact_secrets(combined, pat_token)
    preview, cut = _tail(combined, MAX_OUTPUT_BYTES)
    exit_code = int(result.returncode)
    payload: dict[str, Any] = {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "truncated": cut,
        "output": preview,
        "command": command,
    }
    if needs_pat:
        payload["github_auth"] = "pat_injected"
        reason = git_auth_failure_reason(combined, exit_code)
        if reason:
            payload["reason"] = reason
        if reason == "auth_denied":
            payload["error"] = (
                "GitHub rejected credentials (check github_pat scopes, expiry, SSO, "
                "and that origin uses https://github.com/… not git@github.com)."
            )
    cmd_l = command.lower()
    if "git pull" in cmd_l or cmd_l.strip() == "git pull":
        pull_result = _classify_git_pull_output(combined, exit_code)
        payload["pull_result"] = pull_result
        if exit_code == 0:
            payload["message"] = (
                "Repository is up to date with remote."
                if pull_result == "already_up_to_date"
                else "Git pull completed successfully."
            )
            payload["next_steps"] = [
                "Do NOT run git pull again this session.",
                "Continue with branch checkout and docs/MAINTENANCE_REPORT.md.",
            ]
        else:
            payload["error"] = preview[:500] if preview else f"git pull failed (exit {exit_code})"
    elif exit_code != 0:
        payload["error"] = preview[:500] if preview else f"command failed (exit {exit_code})"
    return json.dumps(payload, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_bash": coding_bash,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_bash",
            "TOOL_DESCRIPTION": "Run a shell command within the coding workspace. ",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Required. Full shell command to run in the workspace (e.g. git status, ls -la). Never omit this field.",
                    },
                    "timeout": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": f"Timeout in seconds (default {DEFAULT_TIMEOUT})",
                    },
                    "workdir": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Working directory relative to coding root",
                    },
                },
                "required": ["command"],
            },
        },
    },
]
