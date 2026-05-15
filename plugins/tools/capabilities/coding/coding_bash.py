"""Execute shell commands within the coding root directory."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
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
    "Supports timeout. Dangerous commands (rm -rf /, etc.) are blocked."
)

DEFAULT_TIMEOUT = 120
MAX_OUTPUT_BYTES = 50_000

_BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "chmod -R 777 /",
    "dd if=/dev/zero",
    "mkfs",
    "fdisk",
    "parted",
    "iptables",
    "ufw",
})

_BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",           # rm -rf anything at root
    r"rm\s+-rf\s+\*",         # rm -rf *
    r"rm\s+-R\s+/",          # rm -R recursive
    r"wget\s+.*\|\s*sh",      # wget | sh (remote execution)
    r"curl\s+.*\|\s*sh",      # curl | sh
    r":\(\)\s*:",             # fork bomb :(){:|:&};:
    r"fork\(\)",               # fork()
    r"\$\s*\(\s*\$\s*\)",   # $() subshell loops
    r"dd\s+if=/dev/zero",     # disk wipe
    r"dd\s+if=/dev/urandom",  # random disk write
    r">\s*/dev/sd[a-z]",     # write to disk device
    r"chmod\s+-R\s+777",    # chmod 777 recursive
    r"chown\s+-R",           # chown recursive
    r"mv\s+/.*\s+/bin",    # move to bin
    r"cp\s+.*\s+/bin",    # copy to bin
    r"ln\s+-s",            # symlink attack
    r":\|",                 # pipe fork bomb pattern
    r"while\s+.*do\s+.*done", # infinite loop potential
]

_BLOCKED_REGEX = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

_VALIDATION_COMMANDS = frozenset({
    "ruff",
    "python -m py_compile",
    "pip check",
    "npm test",
    "npm run",
    "npm run build",
    "npm run lint",
    "npm run typecheck",
    "npm run type-check",
    "npx",
    "pnpm",
    "yarn",
    "pip install",
    "pip uninstall",
})


def _is_blocked(command: str) -> str | None:
    lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in lower:
            return f"command blocked: '{blocked}' is not allowed (1)"
    
    for i, regex in enumerate(_BLOCKED_REGEX):
        if regex.search(lower):
            return f"command blocked: matches dangerous pattern '{_BLOCKED_PATTERNS[i]}' (2)"
    
    return None


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
    blocked = _is_blocked(command)
    if blocked:
        return json.dumps({"ok": False, "error": blocked}, ensure_ascii=False)
    
    workdir_rel = (arguments.get("workdir") or "").strip()
    if workdir_rel:
        workdir_path = Path(workdir_rel)
        if workdir_path.is_absolute():
            raise ValueError(f"workdir must be relative, not absolute: {workdir_rel}")
        cwd = str((root / workdir_path).resolve())
    else:
        cwd = str(root.resolve())
    try:
        timeout_s = max(1, int(arguments.get("timeout", DEFAULT_TIMEOUT)))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT
    env = {
        **os.environ,
        "HOME": str(root),
        "PWD": cwd,
    }
    try:
        result = subprocess.run(
            command,
            shell=True,
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
    combined = ""
    if result.stdout:
        combined += result.stdout
    if result.stderr:
        if combined:
            combined += "\n--- stderr ---\n"
        combined += result.stderr
    if not combined:
        combined = "(no output)"
    preview, cut = _tail(combined, MAX_OUTPUT_BYTES)
    return json.dumps(
        {
            "ok": True,
            "exit_code": result.returncode,
            "truncated": cut,
            "output": preview,
        },
        ensure_ascii=False,
    )


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
