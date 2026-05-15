"""Replace text in a UTF-8 file within the coding root (surgical edit)."""

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


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]


__version__ = "1.0.0"
TOOL_ID = "coding_replace"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding replace", "edit file", "patch code", "surgical edit")
TOOL_CAPABILITIES = ("coding.write",)
TOOL_LABEL = "Coding: Replace text"
TOOL_DESCRIPTION = (
    "Replace old_string with new_string in a file within the coding workspace. "
    "Unless replace_all is true, old_string must match exactly once. "
    "Use coding_write_file to create or overwrite entire files."
)

MAX_BYTES = config.CODING_MAX_FILE_BYTES


def coding_replace(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return json.dumps({"ok": False, "error": "path is required"}, ensure_ascii=False)
    resolved = (root / rel).resolve()
    old = arguments.get("old_string")
    new = arguments.get("new_string")
    if old is None:
        return json.dumps({"ok": False, "error": "old_string is required"}, ensure_ascii=False)
    if new is None:
        new = ""
    if not resolved.is_file():
        return json.dumps(
            {"ok": False, "error": "not a regular file", "path": rel},
            ensure_ascii=False,
        )
    try:
        raw = resolved.read_bytes()
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    if len(raw) > MAX_BYTES:
        return json.dumps({"ok": False, "error": "file too large"}, ensure_ascii=False)
    if not is_probably_text(raw):
        return json.dumps({"ok": False, "error": "refusing to edit binary file"}, ensure_ascii=False)
    text = raw.decode("utf-8", errors="strict")
    old_s = str(old)
    new_s = str(new)
    count = text.count(old_s)
    if count == 0:
        return json.dumps(
            {"ok": False, "error": "old_string not found", "path": rel},
            ensure_ascii=False,
        )
    try:
        replace_all = bool(arguments.get("replace_all", False))
    except Exception:
        replace_all = False
    if not replace_all and count != 1:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    f"old_string matches {count} times; set replace_all true to replace all, "
                    "or make old_string unique"
                ),
                "matches": count,
            },
            ensure_ascii=False,
        )
    if replace_all:
        updated = text.replace(old_s, new_s)
        replaced = count
    else:
        updated = text.replace(old_s, new_s, 1)
        replaced = 1
    try:
        resolved.write_text(updated, encoding="utf-8", newline="")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "replacements": replaced,
            "bytes_written": len(updated.encode("utf-8")),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_replace": coding_replace,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_replace",
            "TOOL_DESCRIPTION": "Replace old_string with new_string in a file within the coding workspace. "
            "Unless replace_all is true, old_string must match exactly once. "
            "Use coding_write_file to create or overwrite entire files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path relative to coding root",
                    },
                    "old_string": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Exact text to replace (must match once unless replace_all)",
                    },
                    "new_string": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Replacement text (may be empty to delete)",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Replace every occurrence (default false)",
                    },
                },
                "required": ["path", "old_string"],
            },
        },
    },
]
