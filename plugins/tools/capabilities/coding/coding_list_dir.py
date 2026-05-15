"""List files and directories within the coding root."""

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

__version__ = "1.0.0"
TOOL_ID = "coding_list"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding list", "list files", "list directory")
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: List directory"
TOOL_DESCRIPTION = (
    "List files and subdirectories within the coding workspace. "
    "Paths are relative to the coding root. Truncates after many entries."
)

MAX_ENTRIES = config.WORKSPACE_MAX_LIST_ENTRIES


def coding_list_dir(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    rel = (arguments.get("path") or "").strip() or "."
    if rel == ".":
        resolved = root
    else:
        resolved = (root / rel).resolve()
    if not resolved.is_dir():
        return json.dumps(
            {"ok": False, "error": "not a directory", "path": rel},
            ensure_ascii=False,
        )
    try:
        want_files = bool(arguments.get("include_files", True))
        want_dirs = bool(arguments.get("include_directories", True))
    except Exception:
        want_files, want_dirs = True, True
    entries: list[dict[str, Any]] = []
    try:
        for name in sorted(os.listdir(resolved)):
            if name in (".", ".."):
                continue
            fp = resolved / name
            try:
                is_dir = fp.is_dir()
                is_link = fp.is_symlink()
            except OSError:
                continue
            if is_dir and not want_dirs:
                continue
            if not is_dir and not want_files:
                continue
            rel_child = str(Path(rel) / name) if rel not in (".", "") else name
            entries.append(
                {
                    "name": name,
                    "path": rel_child.replace("\\", "/"),
                    "is_dir": is_dir,
                    "is_symlink": is_link,
                }
            )
            if len(entries) >= MAX_ENTRIES:
                break
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps(
        {
            "ok": True,
            "path": rel.replace("\\", "/"),
            "entries": entries,
            "truncated": len(entries) >= MAX_ENTRIES,
            "max_entries": MAX_ENTRIES,
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_list_dir": coding_list_dir,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_list_dir",
            "TOOL_DESCRIPTION": "List files and subdirectories within the coding workspace. "
            "Paths are relative to the coding root. Truncates after many entries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Directory path relative to coding root (default: root)",
                    },
                    "include_files": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Include files (default true)",
                    },
                    "include_directories": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Include directories (default true)",
                    },
                },
            },
        },
    },
]
