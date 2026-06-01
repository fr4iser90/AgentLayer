"""Read-only Git inspection inside the coding workspace (no fetch/push/commit)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.coding.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

__version__ = "1.0.0"
TOOL_ID = "git_read"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "github"
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


def _safe_git_ref(raw: Any) -> str | None:
    if raw is None:
        return None
    ref = str(raw).strip()
    if not ref or ref.startswith("-"):
        return None
    if any(ch in ref for ch in (";", "|", "&", "$", "`", "\n", "\r", "\x00")):
        return None
    return ref


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


def git_read(arguments: dict[str, Any], context: dict | None = None) -> str:
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
        preview, cut = _tail(out, MAX_OUTPUT_BYTES)
        branch_name: str | None = None
        clean = True
        for line in (out or "").splitlines():
            if line.startswith("## "):
                branch_name = line[3:].strip().split("...")[0].strip() or None
            elif line.strip():
                clean = False
        if branch_name is None:
            cbr, br_out, _ = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=timeout_s)
            if cbr == 0:
                branch_name = (br_out or "").strip() or None
        payload: dict[str, Any] = {
            "ok": code == 0,
            "operation": op,
            "exit_code": code,
            "output": preview,
            "truncated": cut,
            "branch": branch_name,
            "clean": clean,
            "message": (
                f"On branch {branch_name or '?'}; working tree clean."
                if clean
                else f"On branch {branch_name or '?'}; working tree has uncommitted changes."
            ),
        }
        return json.dumps(payload, ensure_ascii=False)
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
        since_ref = _safe_git_ref(arguments.get("since_ref"))
        until_ref = _safe_git_ref(arguments.get("until_ref"))
        if arguments.get("since_ref") and since_ref is None:
            return json.dumps(
                {"ok": False, "error": "since_ref must be a safe git ref (tag, branch, or SHA)"},
                ensure_ascii=False,
            )
        if arguments.get("until_ref") and until_ref is None:
            return json.dumps(
                {"ok": False, "error": "until_ref must be a safe git ref (tag, branch, or SHA)"},
                ensure_ascii=False,
            )
        rev_range: str | None = None
        if since_ref and until_ref:
            rev_range = f"{since_ref}..{until_ref}"
        elif since_ref:
            rev_range = f"{since_ref}..HEAD"
        elif until_ref:
            rev_range = until_ref
        log_args = [
            "log",
            f"-n{n}",
            "--no-color",
            "--date=short",
            "--pretty=format:%h %ad %d %s",
        ]
        if rev_range:
            log_args.append(rev_range)
        code, out, _ = _run_git(root, log_args, timeout=timeout_s)
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
    payload = {
        "ok": code == 0,
        "operation": op,
        "exit_code": code,
        "output": preview,
        "truncated": cut,
    }
    if op == "log":
        if since_ref:
            payload["since_ref"] = since_ref
        if until_ref:
            payload["until_ref"] = until_ref
        if rev_range:
            payload["rev_range"] = rev_range
    return json.dumps(payload, ensure_ascii=False)



def tool_step_detail(arguments: dict[str, Any]) -> str:
    op = str(arguments.get("operation") or arguments.get("subcommand") or "").strip()
    path = str(arguments.get("path") or "").strip().replace("\\", "/")
    if op and path:
        return f"{op} {path.rsplit('/', 1)[-1]}"
    return op or path


HANDLERS: dict[str, Callable[..., str]] = {
    "git_read": git_read,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "git_read",
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
                    "since_ref": {
                        "type": "string",
                        "description": (
                            "For log: start ref for changelog range (e.g. v1.0.0); "
                            "uses since_ref..HEAD when until_ref is omitted"
                        ),
                    },
                    "until_ref": {
                        "type": "string",
                        "description": "For log: end ref (optional; with since_ref uses since_ref..until_ref)",
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
