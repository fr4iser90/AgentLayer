"""Glob files matching a pattern within the coding root."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config as _global_config

from plugins.tools.workspace.lib.common import (
    json_workspace_missing_error,
    workspace_binding_from_context,
)

__version__ = "1.0.0"
TOOL_ID = "glob"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
# Router phrases: co-located glob.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("coding.read",)
TOOL_LABEL = "Coding: Glob"
TOOL_DESCRIPTION = (
    "Find files in the coding workspace using glob pattern (like **/*.py). "
    "Results sorted by modification time."
)

MAX_FILES = _global_config.WORKSPACE_MAX_GLOB_FILES


def glob(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    pattern = (arguments.get("pattern") or "").strip()
    if not pattern:
        path_given = arguments.get("path")
        if path_given and isinstance(path_given, str) and path_given.strip():
            pattern = path_given.strip()
        else:
            return json.dumps({
                "ok": False,
                "error": "pattern is required. Use glob like **/*.py"
            }, ensure_ascii=False)
    path_rel = (arguments.get("path") or "").strip() or "."
    if path_rel == ".":
        resolved = root
    else:
        resolved = (root / path_rel).resolve()
    if not resolved.is_dir():
        return json.dumps(
            {"ok": False, "error": "path must be a directory"},
            ensure_ascii=False,
        )
    matches: list[dict[str, Any]] = []
    try:
        root_r = root.resolve()
        for p in resolved.glob(pattern):
            if not p.is_file():
                continue
            try:
                real = p.resolve()
                real.relative_to(root_r)
            except (ValueError, OSError):
                continue
            try:
                rel = real.relative_to(resolved)
            except ValueError:
                continue
            try:
                st = p.stat()
                mtime = st.st_mtime
                size = st.st_size
            except OSError:
                mtime = 0
                size = 0
            matches.append({
                "path": str(rel).replace("\\", "/"),
                "full_path": str(real).replace("\\", "/"),
                "size_bytes": size,
                "mtime": mtime,
            })
            if len(matches) >= MAX_FILES:
                break
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    matches.sort(key=lambda m: m["mtime"], reverse=True)
    truncated = len(matches) >= MAX_FILES
    if truncated:
        matches = matches[:MAX_FILES]
    out = [m["path"] for m in matches]
    hint = None
    if truncated:
        hint = (
            f"Results capped at {MAX_FILES} files (WORKSPACE_MAX_GLOB_FILES / config). "
            "Use a narrower glob or a subdirectory `path`."
        )
    payload: dict[str, Any] = {
        "ok": True,
        "pattern": pattern,
        "path": path_rel.replace("\\", "/"),
        "files": out,
        "truncated": truncated,
        "max_files": MAX_FILES,
        "count": len(out),
    }
    if hint:
        payload["truncation_hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


def tool_step_detail(arguments: dict[str, Any]) -> str:
    return str(arguments.get("pattern") or "").strip()


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "glob": glob,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. **/*.py or src/**/*.ts",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
]
