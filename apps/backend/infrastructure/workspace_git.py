"""Read-only Git inspection for workspace paths (HTTP API; mirrors ``coding_git_read``)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

MAX_OUTPUT_BYTES = 80_000
DEFAULT_TIMEOUT = 45

_DIFF_STAT_LINE = re.compile(r"^\s*(.+?)\s+\|\s+(.+)$")


def _tail(text: str, max_bytes: int) -> tuple[str, bool]:
    raw = text or ""
    b = raw.encode("utf-8")
    if len(b) <= max_bytes:
        return raw, False
    return raw.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace") + "\n…[truncated]", True


def git_repo_ok(root: Path) -> tuple[bool, str | None]:
    if not shutil.which("git"):
        return False, "git binary not found in PATH"
    if not (root / ".git").exists():
        return False, "not a git repository (no .git in workspace root)"
    return True, None


def safe_rel_git_path(raw: str | None) -> str | None:
    if raw is None:
        return None
    p = str(raw).strip().replace("\\", "/")
    if not p or ".." in p or p.startswith("/"):
        return None
    return p


def run_git(root: Path, args: list[str], *, timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str, str]:
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


def parse_diff_stat_files(stat_output: str) -> list[dict[str, str]]:
    """Parse ``git diff --stat`` file lines into ``{path, stat}`` entries."""
    files: list[dict[str, str]] = []
    for line in (stat_output or "").splitlines():
        m = _DIFF_STAT_LINE.match(line)
        if not m:
            continue
        path = m.group(1).strip()
        if not path:
            continue
        files.append({"path": path, "stat": m.group(2).strip()})
    return files


def workspace_git_branch(root: Path) -> str | None:
    code, out, _ = run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if code != 0:
        return None
    ref = (out or "").strip()
    return ref or None


def workspace_git_has_changes(root: Path) -> bool:
    code, out, _ = run_git(root, ["status", "--porcelain"])
    if code != 0:
        return False
    return bool((out or "").strip())


def workspace_git_changes_summary(root: Path) -> dict[str, Any]:
    """
    Working-tree change summary: branch, porcelain flag, ``diff --stat`` file list.

    Returns ``ok: false`` when not a git repo or git is missing.
    """
    ok_repo, err = git_repo_ok(root)
    if not ok_repo:
        return {"ok": False, "is_git_repo": False, "error": err}

    branch = workspace_git_branch(root)
    has_changes = workspace_git_has_changes(root)

    code, stat_out, _ = run_git(root, ["diff", "--stat", "--no-color"])
    stat_preview, stat_truncated = _tail(stat_out, MAX_OUTPUT_BYTES)
    files = parse_diff_stat_files(stat_out)

    return {
        "ok": code == 0,
        "is_git_repo": True,
        "branch": branch,
        "has_changes": has_changes,
        "stat": stat_preview,
        "stat_truncated": stat_truncated,
        "files": files,
        "exit_code": code,
    }


def workspace_git_file_diff(root: Path, rel_path: str) -> dict[str, Any]:
    """Unified diff for one file (or entire tree when ``rel_path`` is empty — not used by API)."""
    ok_repo, err = git_repo_ok(root)
    if not ok_repo:
        return {"ok": False, "is_git_repo": False, "error": err}

    safe = safe_rel_git_path(rel_path)
    if safe is None:
        return {"ok": False, "is_git_repo": True, "error": "path must be a safe relative path (no .. or absolute)"}

    args = ["diff", "--no-color", "--", safe]
    code, out, _ = run_git(root, args)
    preview, truncated = _tail(out, MAX_OUTPUT_BYTES)
    return {
        "ok": code == 0,
        "is_git_repo": True,
        "path": safe,
        "diff": preview,
        "diff_truncated": truncated,
        "has_changes": bool((out or "").strip()),
        "exit_code": code,
    }
