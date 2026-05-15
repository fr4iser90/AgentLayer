"""Read-only Git inspection inside the coding workspace (no fetch/push/commit)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

__version__ = "1.0.0"
TOOL_ID = "coding_git_read"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("git status", "git log", "git diff", "current branch", "repository")
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Git (read-only)"
TOOL_DESCRIPTION = (
    "Run **read-only** Git commands in the workspace root: `status`, `branch`, `log`, `diff`, or `diff_stat`. "
    "Uses `git -C <workspace>` (no shell). Optional `path` for `diff` must be relative (no `..`). "
    "Does not fetch, pull, push, or commit."
)

MAX_OUTPUT_BYTES = 80_000
DEFAULT_TIMEOUT = 45
MAX_LOG_COMMITS = 100


def _tail(text: str, max_bytes: int) -> tuple[str, bool]:
    raw = text or ""
    b = raw.encode("utf-8")
    if len(b) <= max_bytes:
        return raw, False
    return raw.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace") + "\n…[truncated]", True


def _git_ok(root: Path) -> tuple[bool, str | None]:
    if not shutil.which("git"):
        return False, "git binary not found in PATH"
    if not (root / ".git").exists():
        return False, "not a git repository (no .git in workspace root)"
    return True, None


def _safe_rel_path(raw: Any) -> str | None:
    if raw is None:
        return None
    p = str(raw).strip().replace("\\", "/")
    if not p or ".." in p or p.startswith("/"):
        return None
    return p


def _run_git(
    root: Path,
    args: list[str],
    *,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, str, str]:
    cmd = ["git", "-C", str(root.resolve()), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)
    out = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
    return proc.returncode, out, proc.stderr or ""


def coding_git_read(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"]).resolve()
    ok, err = _git_ok(root)
    if not ok:
        return json.dumps({"ok": False, "error": err}, ensure_ascii=False)

    op = str(arguments.get("operation") or "status").strip().lower()
    allowed = frozenset({"status", "branch", "log", "diff", "diff_stat"})
    if op not in allowed:
        return json.dumps(
            {
                "ok": False,
                "error": f"operation must be one of: {', '.join(sorted(allowed))}",
            },
            ensure_ascii=False,
        )

    try:
        timeout_s = max(5, min(int(arguments.get("timeout", DEFAULT_TIMEOUT)), 120))
    except (TypeError, ValueError):
        timeout_s = DEFAULT_TIMEOUT

    if op == "status":
        code, out, _ = _run_git(root, ["status", "--porcelain=v1", "-b"], timeout=timeout_s)
    elif op == "branch":
        c1, ref, _ = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=timeout_s)
        c2, short, _ = _run_git(root, ["rev-parse", "--short", "HEAD"], timeout=timeout_s)
        c3, sb, _ = _run_git(root, ["status", "-sb"], timeout=timeout_s)
        out = (
            f"ref: {(ref or '').strip()}\n"
            f"short: {(short or '').strip()}\n"
            f"status:\n{(sb or '').strip()}"
        )
        code = 0 if c1 == c2 == c3 == 0 else max(c1, c2, c3)
    elif op == "log":
        try:
            n = int(arguments.get("max_commits", 25))
        except (TypeError, ValueError):
            n = 25
        n = max(1, min(n, MAX_LOG_COMMITS))
        code, out, _ = _run_git(
            root,
            [
                "log",
                f"-n{n}",
                "--no-color",
                "--date=short",
                "--pretty=format:%h %ad %d %s",
            ],
            timeout=timeout_s,
        )
    elif op == "diff_stat":
        code, out, _ = _run_git(root, ["diff", "--stat", "--no-color"], timeout=timeout_s)
    else:  # diff
        rel = _safe_rel_path(arguments.get("path"))
        if rel is None and arguments.get("path"):
            return json.dumps(
                {"ok": False, "error": "path must be a safe relative path (no .. or absolute)"},
                ensure_ascii=False,
            )
        args = ["diff", "--no-color"]
        if rel:
            args.extend(["--", rel])
        code, out, _ = _run_git(root, args, timeout=timeout_s)

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
    "coding_git_read": coding_git_read,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_git_read",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "description": "One of: status, branch, log, diff, diff_stat",
                    },
                    "max_commits": {
                        "type": "integer",
                        "description": "For log: number of commits (1–100, default 25)",
                    },
                    "path": {
                        "type": "string",
                        "description": "For diff only: single relative file path under the repo",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout seconds (5–120, default 45)",
                    },
                },
            },
        },
    },
]
