"""Read a UTF-8 text file within the coding root with optional line windowing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config

from plugins.tools.agent.core.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]

__version__ = "1.0.0"
TOOL_ID = "coding_read"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding read", "read code", "view file")
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Read file"
TOOL_DESCRIPTION = (
    "Read a UTF-8 text file within the coding workspace. "
    "Paths are relative to the coding root. Supports start_line and limit_lines for large files."
)

MAX_BYTES = config.CODING_MAX_FILE_BYTES
MAX_LINES = config.WORKSPACE_MAX_READ_LINES


def coding_read_file(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "coding_read_file requires a non-empty string field \"path\" (file path relative to workspace root). "
                    'Example: {"path": "README.md"} or {"path": "src/app.ts", "start_line": 1, "limit_lines": 80}'
                ),
            },
            ensure_ascii=False,
        )
    resolved = (root / rel).resolve()
    if not resolved.is_file():
        return json.dumps(
            {"ok": False, "error": "not a regular file", "path": rel},
            ensure_ascii=False,
        )
    try:
        size = os.path.getsize(resolved)
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    if size > MAX_BYTES:
        return json.dumps(
            {"ok": False, "error": f"file too large (>{MAX_BYTES} bytes)", "size": size},
            ensure_ascii=False,
        )
    try:
        raw = resolved.read_bytes()
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    if not is_probably_text(raw):
        return json.dumps(
            {"ok": False, "error": "file looks binary; not returned as text"},
            ensure_ascii=False,
        )
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    start = 1
    limit = arguments.get("limit_lines")
    raw_start = arguments.get("start_line")
    if raw_start is not None:
        try:
            start = max(1, int(raw_start))
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "start_line must be an integer"}, ensure_ascii=False)
    if limit is not None:
        try:
            lim = max(0, int(limit))
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "limit_lines must be an integer"}, ensure_ascii=False)
        chunk = lines[start - 1 : start - 1 + lim]
        body = "".join(chunk)
        return json.dumps(
            {
                "ok": True,
                "path": rel.replace("\\", "/"),
                "start_line": start,
                "line_count_total": len(lines),
                "content": body,
                "truncated_lines": (start - 1 + len(chunk)) < len(lines),
            },
            ensure_ascii=False,
        )
    if len(lines) > MAX_LINES:
        body = "".join(lines[:MAX_LINES])
        return json.dumps(
            {
                "ok": True,
                "path": rel.replace("\\", "/"),
                "content": body,
                "truncated": True,
                "line_count_total": len(lines),
                "max_lines": MAX_LINES,
            },
            ensure_ascii=False,
        )
    return json.dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "content": text,
            "truncated": False,
            "line_count_total": len(lines),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_read_file": coding_read_file,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_read_file",
            "TOOL_DESCRIPTION": "Read a UTF-8 text file within the coding workspace. "
            "Paths are relative to the coding root. Supports start_line and limit_lines for large files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path relative to coding root",
                    },
                    "start_line": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "1-based line to start from (default 1)",
                    },
                    "limit_lines": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "If set, return only this many lines from start_line",
                    },
                },
                "required": ["path"],
            },
        },
    },
]
