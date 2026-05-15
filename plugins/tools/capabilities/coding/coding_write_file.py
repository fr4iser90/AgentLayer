"""Create or overwrite a UTF-8 text file within the coding root."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config

from plugins.tools.capabilities.coding.coding_common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)


def coalesce_content(arguments: dict[str, Any]) -> tuple[str, str | None]:
    for key in ("content", "text", "source"):
        v = arguments.get(key)
        if v is not None:
            s = str(v)
            return s, None
    return "", "content is required (use 'content', 'text', or 'source' key)"

__version__ = "1.0.0"
TOOL_ID = "coding_write"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding write", "write code", "create file")
TOOL_CAPABILITIES = ("coding.write",)
TOOL_LABEL = "Coding: Write file"
TOOL_DESCRIPTION = (
    "Create or overwrite a text file within the coding workspace. "
    "Paths are relative to the coding root; cannot escape to system or tool directories. "
    "Creates parent directories automatically. Use coding_replace for surgical edits."
)

MAX_BYTES = config.CODING_MAX_FILE_BYTES


def coding_write_file(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return json.dumps({"ok": False, "error": "path is required"}, ensure_ascii=False)
    resolved = (root / rel).resolve()
    content, cerr = coalesce_content(arguments)
    if cerr:
        return json.dumps({"ok": False, "error": cerr}, ensure_ascii=False)
    data = content.encode("utf-8")
    if len(data) > MAX_BYTES:
        return json.dumps(
            {"ok": False, "error": f"content too large (>{MAX_BYTES} bytes)"},
            ensure_ascii=False,
        )
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8", newline="")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "bytes_written": len(data),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_write_file": coding_write_file,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_write_file",
            "TOOL_DESCRIPTION": "Create or overwrite a text file within the coding workspace. "
            "Paths are relative to the coding root; cannot escape to system or tool directories. "
            "Creates parent directories automatically. Use coding_replace for surgical edits.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path relative to coding root (e.g. src/main.py)",
                    },
                    "content": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Full file contents (UTF-8 text)",
                    },
                    "text": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alias for content",
                    },
                    "source": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alias for content",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
]
