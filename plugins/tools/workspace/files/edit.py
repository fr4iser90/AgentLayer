"""Smart edit with multiple fallback replacers for robust file editing."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config

from apps.backend.domain.coding.common import (
    is_blocked_credential_path,
    json_blocked_credential_path_error,
    json_workspace_missing_error,
    maybe_enqueue_incremental_index,
    workspace_binding_from_context,
)

def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]

__version__ = "1.0.0"
TOOL_ID = "edit"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "repository"
TOOL_TRIGGERS = ("coding edit", "smart edit", "edit file")
TOOL_CAPABILITIES = ("coding.write",)
TOOL_LABEL = "Coding: Smart edit"
TOOL_DESCRIPTION = (
    "Edit a file by replacing old_string with new_string. "
    "Uses multiple fallback strategies: exact match, line-trimmed, block-anchor, "
    "whitespace-normalized, indentation-flexible. "
    "Unlike coding_replace, this is more forgiving with whitespace differences."
)

MAX_BYTES = config.CODING_MAX_FILE_BYTES


def _simple_replace(content: str, find: str) -> str | None:
    idx = content.find(find)
    if idx >= 0:
        last = content.rfind(find)
        if idx == last:
            return content[:idx] + "{{{REPLACEMENT}}}" + content[idx + len(find):]
    return None


def _line_trimmed_replace(content: str, find: str) -> str | None:
    old_lines = content.split("\n")
    search_lines = find.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines = search_lines[:-1]
    for i in range(len(old_lines) - len(search_lines) + 1):
        if all(
            old_lines[i + j].strip() == search_lines[j].strip()
            for j in range(len(search_lines))
        ):
            start = sum(len(old_lines[k]) + 1 for k in range(i))
            end = start + sum(len(old_lines[i + j]) + 1 for j in range(len(search_lines))) - 1
            return content[:start] + "{{{REPLACEMENT}}}" + content[end:]
    return None


def _block_anchor_replace(content: str, find: str) -> str | None:
    old_lines = content.split("\n")
    search_lines = find.split("\n")
    if search_lines and search_lines[-1] == "":
        search_lines = search_lines[:-1]
    if len(search_lines) < 3:
        return None
    first = search_lines[0].strip()
    last = search_lines[-1].strip()
    for i in range(len(old_lines)):
        if old_lines[i].strip() != first:
            continue
        for j in range(i + 2, len(old_lines)):
            if old_lines[j].strip() == last:
                start = sum(len(old_lines[k]) + 1 for k in range(i))
                end = sum(len(old_lines[k]) + 1 for k in range(j + 1)) - 1
                return content[:start] + "{{{REPLACEMENT}}}" + content[end:]
    return None


def _whitespace_replace(content: str, find: str) -> str | None:
    def normalize(s: str) -> str:
        return " ".join(s.split())
    nf = normalize(find)
    for i in range(len(content)):
        for j in range(i + 1, len(content) + 1):
            if normalize(content[i:j]) == nf:
                return content[:i] + "{{{REPLACEMENT}}}" + content[j:]
    return None


def _apply_edit(content: str, old: str, new: str, replace_all: bool) -> tuple[str, list[str]]:
    strategies = [
        ("exact", _simple_replace),
        ("line_trimmed", _line_trimmed_replace),
        ("block_anchor", _block_anchor_replace),
        ("whitespace_normalized", _whitespace_replace),
    ]
    for name, fn in strategies:
        result = fn(content, old)
        if result is not None:
            if replace_all:
                return content.replace(old, new), []
            return result.replace("{{{REPLACEMENT}}}", new, 1), []
    errors = [
        f"Could not find old_string with {s[0]} matching strategy"
        for s in strategies
    ]
    return content, errors


def edit(arguments: dict[str, Any], context: dict | None = None) -> str:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return json_workspace_missing_error()
    root = Path(ws["path"])
    
    rel = (arguments.get("path") or "").strip()
    if not rel:
        return json.dumps({"ok": False, "error": "path is required"}, ensure_ascii=False)
    if is_blocked_credential_path(rel):
        return json_blocked_credential_path_error(rel)
    resolved = (root / rel).resolve()
    old = arguments.get("old_string")
    new = arguments.get("new_string")
    if old is None:
        return json.dumps({"ok": False, "error": "old_string is required"}, ensure_ascii=False)
    if new is None:
        new = ""
    if old == new:
        return json.dumps({"ok": False, "error": "old_string and new_string are identical"}, ensure_ascii=False)
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
    content = raw.decode("utf-8", errors="strict")
    replace_all = bool(arguments.get("replace_all", False))
    updated, errors = _apply_edit(content, str(old), str(new), replace_all)
    if errors:
        return json.dumps(
            {
                "ok": False,
                "error": "; ".join(errors),
                "hint": "Ensure old_string matches the file content exactly or with similar whitespace/indentation.",
            },
            ensure_ascii=False,
        )
    try:
        resolved.write_text(updated, encoding="utf-8", newline="")
    except OSError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    rel_norm = rel.replace("\\", "/")
    maybe_enqueue_incremental_index(context, [rel_norm])
    return json.dumps(
        {
            "ok": True,
            "path": rel_norm,
            "bytes_written": len(updated.encode("utf-8")),
        },
        ensure_ascii=False,
    )


def tool_step_detail(arguments: dict[str, Any]) -> str:
    path = str(arguments.get("path") or "").strip().replace("\\", "/")
    return path.rsplit("/", 1)[-1] if path else ""


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "edit": edit,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "edit",
            "TOOL_DESCRIPTION": "Edit a file by replacing old_string with new_string. "
            "Uses multiple fallback strategies: exact match, line-trimmed, block-anchor, "
            "whitespace-normalized, indentation-flexible. "
            "Unlike coding_replace, this is more forgiving with whitespace differences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path relative to coding root",
                    },
                    "old_string": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "The text to replace (matched with flexible strategies)",
                    },
                    "new_string": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "The replacement text (may be empty to delete)",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Replace all occurrences (default false = require single match)",
                    },
                },
                "required": ["path", "old_string"],
            },
        },
    },
]
