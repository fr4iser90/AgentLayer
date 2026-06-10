"""Search file contents (substring or regex) within the coding root."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config as _global_config

from apps.backend.domain.coding.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]


__version__ = "1.0.0"
TOOL_ID = "search"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
# Router phrases: co-located search.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Search files"
TOOL_DESCRIPTION = (
    "Search file contents (literal substring or regex) within the coding workspace. "
    "Literal mode may use ripgrep when available. Skips binary and oversized files. Match and file limits apply."
)

MAX_FILES = _global_config.WORKSPACE_MAX_SEARCH_FILES
MAX_MATCHES = _global_config.WORKSPACE_MAX_SEARCH_MATCHES
MAX_FILE_BYTES = _global_config.WORKSPACE_SEARCH_MAX_FILE_BYTES


def _rg_max_filesize_flag(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{max(n // (1024 * 1024), 1)}M"
    return f"{max(n // 1024, 1)}K"


_RG_LINE_RE = re.compile(r"^(?P<path>.+):(?P<line>\d+):(?P<text>.*)$")


def _parse_ripgrep_line(line: str) -> tuple[str, int, str] | None:
    """Parse ``path:line:text``; handles trailing colons in matched source lines."""
    m = _RG_LINE_RE.match(line.strip())
    if not m:
        return None
    try:
        return m.group("path"), int(m.group("line")), m.group("text")
    except ValueError:
        return None


def _literal_search_via_ripgrep(
    *,
    needle: str,
    search_root: Path,
    max_matches: int,
    max_files: int,
) -> dict[str, Any] | None:
    if not _global_config.AGENT_CODING_SEARCH_USE_RIPGREP:
        return None
    if "\n" in needle or "\r" in needle:
        return None
    if len(needle) > 2048:
        return None
    rg_exe = (_global_config.AGENT_RIPGREP_PATH or "").strip() or shutil.which("rg")
    if not rg_exe:
        return None
    try:
        proc = subprocess.run(
            [
                rg_exe,
                "-n",
                "--no-heading",
                "--color",
                "never",
                "--fixed-strings",
                "--max-filesize",
                _rg_max_filesize_flag(MAX_FILE_BYTES),
                "--glob",
                "!.git/**",
                "--glob",
                "!**/node_modules/**",
                "--",
                needle,
                str(search_root.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=int(_global_config.AGENT_RIPGREP_TIMEOUT_SEC),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode not in (0, 1):
        return None
    matches_out: list[dict[str, Any]] = []
    files_seen: set[str] = set()
    files_scanned = 0
    truncated_scan = False
    for line in (proc.stdout or "").splitlines():
        if len(matches_out) >= max_matches:
            break
        if not line.strip():
            continue
        parsed = _parse_ripgrep_line(line)
        if parsed is None:
            continue
        path_part, line_no, text = parsed
        try:
            rel = os.path.relpath(path_part, search_root.resolve()).replace("\\", "/")
        except ValueError:
            rel = path_part.replace("\\", "/")
        if rel not in files_seen and len(files_seen) >= max_files:
            truncated_scan = True
            break
        files_seen.add(rel)
        files_scanned = len(files_seen)
        matches_out.append(
            {
                "path": rel,
                "line": line_no,
                "text": text if len(text) <= 500 else text[:500] + "\u2026",
            }
        )
    tm = len(matches_out) >= max_matches
    ts = truncated_scan or files_scanned > max_files
    hint_parts: list[str] = []
    if tm:
        hint_parts.append(
            f"match list capped at {max_matches} (WORKSPACE_MAX_SEARCH_MATCHES); narrow `query` or `path_prefix`."
        )
    if ts:
        hint_parts.append(
            f"file scan limited after {max_files} distinct files (WORKSPACE_MAX_SEARCH_FILES); narrow `path_prefix`."
        )
    payload: dict[str, Any] = {
        "ok": True,
        "query": needle,
        "regex": False,
        "path_prefix": None,
        "matches": matches_out,
        "files_scanned": files_scanned,
        "truncated_matches": tm,
        "truncated_scan": ts,
        "limits": {
            "max_matches": max_matches,
            "max_files_scanned": max_files,
        },
        "search_engine": "ripgrep",
    }
    if hint_parts:
        payload["truncation_hint"] = " ".join(hint_parts)
    return payload


def _python_walk_search(
    *,
    query: Any,
    use_regex: bool,
    search_root: Path,
    rel_root: str,
    cre: re.Pattern[str] | None,
    needle: str,
) -> dict[str, Any]:
    matches_out: list[dict[str, Any]] = []
    files_scanned = 0

    def rel_path_from(full: Path) -> str:
        try:
            return os.path.relpath(full, search_root).replace("\\", "/")
        except ValueError:
            return str(full)

    try:
        for dirpath, _dirnames, filenames in os.walk(search_root):
            for fn in sorted(filenames):
                if len(matches_out) >= MAX_MATCHES:
                    break
                fp = Path(dirpath) / fn
                if not fp.is_file():
                    continue
                try:
                    st = fp.stat()
                except OSError:
                    continue
                if st.st_size > MAX_FILE_BYTES:
                    continue
                files_scanned += 1
                if files_scanned > MAX_FILES:
                    break
                try:
                    raw = fp.read_bytes()
                except OSError:
                    continue
                if not is_probably_text(raw):
                    continue
                text = raw.decode("utf-8", errors="replace")
                lines = text.splitlines()
                for i, line in enumerate(lines, start=1):
                    if len(matches_out) >= MAX_MATCHES:
                        break
                    if use_regex:
                        assert cre is not None
                        if not cre.search(line):
                            continue
                    else:
                        if needle not in line:
                            continue
                    matches_out.append(
                        {
                            "path": rel_path_from(fp),
                            "line": i,
                            "text": line if len(line) <= 500 else line[:500] + "\u2026",
                        }
                    )
            if len(matches_out) >= MAX_MATCHES or files_scanned > MAX_FILES:
                break
    except OSError as e:
        return {"ok": False, "error": str(e)}
    tm = len(matches_out) >= MAX_MATCHES
    ts = files_scanned > MAX_FILES
    hint_parts: list[str] = []
    if tm:
        hint_parts.append(
            f"match list capped at {MAX_MATCHES} (WORKSPACE_MAX_SEARCH_MATCHES); narrow `query` or `path_prefix`."
        )
    if ts:
        hint_parts.append(
            f"file scan stopped after {MAX_FILES} files (WORKSPACE_MAX_SEARCH_FILES); limit directory depth or path_prefix."
        )
    payload: dict[str, Any] = {
        "ok": True,
        "query": str(query),
        "regex": use_regex,
        "path_prefix": rel_root or None,
        "matches": matches_out,
        "files_scanned": files_scanned,
        "truncated_matches": tm,
        "truncated_scan": ts,
        "limits": {
            "max_matches": MAX_MATCHES,
            "max_files_scanned": MAX_FILES,
        },
        "search_engine": "python",
    }
    if hint_parts:
        payload["truncation_hint"] = " ".join(hint_parts)
    return payload


def search(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])

    query = arguments.get("query")
    if query is None or str(query).strip() == "":
        return json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False)
    use_regex = bool(arguments.get("regex", False))
    path_prefix = str(arguments.get("path_prefix") or "").strip()
    search_root = root.resolve()
    rel_root = ""
    if path_prefix:
        sr = (root / path_prefix).resolve()
        if not sr.is_dir():
            return json.dumps(
                {"ok": False, "error": "path_prefix must be a directory"},
                ensure_ascii=False,
            )
        search_root = sr
        rel_root = path_prefix.replace("\\", "/").rstrip("/")
    try:
        if use_regex:
            cre = re.compile(str(query))
        else:
            cre = None
            needle = str(query)
    except re.error as e:
        return json.dumps({"ok": False, "error": f"invalid regex: {e}"}, ensure_ascii=False)

    if not use_regex:
        rg_payload = _literal_search_via_ripgrep(
            needle=needle,
            search_root=search_root,
            max_matches=MAX_MATCHES,
            max_files=MAX_FILES,
        )
        if rg_payload is not None:
            rg_payload["query"] = str(query)
            rg_payload["path_prefix"] = rel_root or None
            return json.dumps(rg_payload, ensure_ascii=False)

    py = _python_walk_search(
        query=query,
        use_regex=use_regex,
        search_root=search_root,
        rel_root=rel_root,
        cre=cre if use_regex else None,
        needle=str(query) if not use_regex else "",
    )
    if py.get("ok") is False:
        return json.dumps(py, ensure_ascii=False)
    return json.dumps(py, ensure_ascii=False)


def tool_step_detail(arguments: dict[str, Any]) -> str:
    q = str(arguments.get("query") or "").strip()
    pp = str(arguments.get("path_prefix") or "").strip()
    if q and pp:
        return f"{q} ({pp})"
    return q or pp


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "search": search,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search file contents (literal substring or regex) within the coding workspace. "
            "Literal mode may use ripgrep when installed. Skips binary and oversized files. Match and file limits apply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for (literal substring unless regex is true)",
                    },
                    "regex": {
                        "type": "boolean",
                        "description": "If true, the query is a Python regex",
                    },
                    "path_prefix": {
                        "type": "string",
                        "description": "Optional subdirectory (relative to coding root) to limit search",
                    },
                },
                "required": ["query"],
            },
        },
    },
]
