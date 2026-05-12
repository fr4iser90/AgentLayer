"""Search file contents (substring or regex) within the coding root."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config as _global_config


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]

__version__ = "1.0.0"
TOOL_ID = "coding_search"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding search", "search code", "grep", "find in files")
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Search files"
TOOL_DESCRIPTION = (
    "Search file contents (literal substring or regex) within the coding workspace. "
    "Skips binary and oversized files. Match and file limits apply."
)

MAX_FILES = _global_config.WORKSPACE_MAX_SEARCH_FILES
MAX_MATCHES = _global_config.WORKSPACE_MAX_SEARCH_MATCHES
MAX_FILE_BYTES = _global_config.WORKSPACE_SEARCH_MAX_FILE_BYTES


def coding_search(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not context or "workspace" not in context:
        return json.dumps({"ok": False, "error": "No workspace in context - agent must inject workspace"}, ensure_ascii=False)
    ws = context["workspace"]
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
            needle = str(query)
    except re.error as e:
        return json.dumps({"ok": False, "error": f"invalid regex: {e}"}, ensure_ascii=False)
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
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "query": str(query),
            "regex": use_regex,
            "path_prefix": rel_root or None,
            "matches": matches_out,
            "files_scanned": files_scanned,
            "truncated_matches": len(matches_out) >= MAX_MATCHES,
            "truncated_scan": files_scanned > MAX_FILES,
            "limits": {
                "max_matches": MAX_MATCHES,
                "max_files_scanned": MAX_FILES,
            },
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_search": coding_search,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_search",
            "description": "Search file contents (literal substring or regex) within the coding workspace. "
            "Skips binary and oversized files. Match and file limits apply.",
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