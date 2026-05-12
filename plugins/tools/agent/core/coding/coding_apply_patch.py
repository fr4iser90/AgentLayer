"""Apply a unified diff patch to a file within the coding root."""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config

def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]

__version__ = "1.0.0"
TOOL_ID = "coding_apply_patch"
TOOL_BUCKET = "files"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding patch", "apply patch", "unified diff")
TOOL_CAPABILITIES = ("coding.write",)
TOOL_LABEL = "Coding: Apply patch"
TOOL_DESCRIPTION = (
    "Apply a unified diff patch to a file. "
    "Patch must be in standard unified diff format (diff --git or ---/+++ headers). "
    "Path in the patch header is resolved relative to the coding root. "
    "Useful for applying code review suggestions or generated patches."
)

MAX_BYTES = config.CODING_MAX_FILE_BYTES


def _parse_patch(patch_text: str) -> list[dict[str, Any]]:
    """Parse unified diff into hunks. Returns list of {path, hunks}."""
    lines = patch_text.splitlines()
    files: list[dict[str, Any]] = []
    current_file: str | None = None
    current_hunks: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git"):
            if current_file is not None and current_hunks:
                files.append({"path": current_file, "hunks": current_hunks})
            parts = line.split()
            if len(parts) >= 3:
                current_file = parts[2].lstrip("b/")
            else:
                current_file = None
            current_hunks = []
        elif line.startswith("--- ") or line.startswith("+++ "):
            pass
        elif line.startswith("@@") and current_file is not None:
            hunk_lines = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("diff --git"):
                hunk_lines.append(lines[i])
                i += 1
            current_hunks.extend(hunk_lines)
            continue
        elif current_file is not None and current_hunks:
            current_hunks.append(line)
        i += 1
    if current_file is not None and current_hunks:
        files.append({"path": current_file, "hunks": current_hunks})
    return files


def _apply_hunks(old_content: str, hunks: list[str]) -> tuple[str, list[str]]:
    """Apply hunks to old_content. Returns (new_content, errors)."""
    old_lines = old_content.splitlines(keepends=True)
    current_line = 0
    new_lines: list[str] = []
    errors: list[str] = []
    i = 0
    while i < len(hunks):
        hunk = hunks[i]
        if not hunk.startswith("@@"):
            i += 1
            continue
        header = hunk
        hunk_body = []
        i += 1
        while i < len(hunks) and not hunks[i].startswith("@@"):
            hunk_body.append(hunks[i])
            i += 1
        try:
            parts = header.split("@@")
            if len(parts) >= 2:
                range_str = parts[1].strip()
                old_range = range_str.split()[0]
                start = int(old_range.lstrip("-").split(",")[0])
            else:
                errors.append(f"invalid hunk header: {header}")
                continue
        except (ValueError, IndexError):
            errors.append(f"invalid hunk header: {header}")
            continue
        target_line = start - 1
        if target_line < 0:
            target_line = 0
        new_lines.extend(old_lines[current_line:target_line])
        current_line = target_line
        for hline in hunk_body:
            if hline.startswith("+"):
                new_lines.append(hline[1:] + ("\n" if not hline.endswith("\n") else ""))
            elif hline.startswith("-"):
                if current_line < len(old_lines):
                    old_l = old_lines[current_line].rstrip("\n")
                    new_l = hline[1:].rstrip("\n")
                    if old_l == new_l:
                        current_line += 1
                    else:
                        errors.append(f"line mismatch at {current_line + 1}: expected {new_l!r}, got {old_l!r}")
                        current_line += 1
                else:
                    errors.append(f"line {current_line + 1} out of range")
            elif hline.startswith(" ") or hline == "":
                current_line += 1
            elif hline.startswith("\\"):
                pass
    new_lines.extend(old_lines[current_line:])
    result = "".join(new_lines)
    if not result.endswith("\n") and old_content.endswith("\n"):
        result += "\n"
    return result, errors


def _generate_diff(old: str, new: str, path: str) -> str:
    """Generate a unified diff between old and new content."""
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))


def coding_apply_patch(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not context or "workspace" not in context:
        return json.dumps({"ok": False, "error": "No workspace in context - agent must inject workspace"}, ensure_ascii=False)
    ws = context["workspace"]
    root = Path(ws["path"])
    
    patch_text = (arguments.get("patch_text") or arguments.get("patch") or "").strip()
    if not patch_text:
        return json.dumps({"ok": False, "error": "patch_text is required"}, ensure_ascii=False)
    files = _parse_patch(patch_text)
    if not files:
        return json.dumps({"ok": False, "error": "no valid hunks found in patch"}, ensure_ascii=False)
    results: list[dict[str, Any]] = []
    all_ok = True
    for file_info in files:
        fpath = file_info["path"]
        resolved = (root / fpath).resolve()
        is_new = not resolved.exists()
        if not is_new:
            if not resolved.is_file():
                results.append({"path": fpath, "ok": False, "error": "not a regular file"})
                all_ok = False
                continue
            try:
                raw = resolved.read_bytes()
            except OSError as e:
                results.append({"path": fpath, "ok": False, "error": str(e)})
                all_ok = False
                continue
            if len(raw) > MAX_BYTES:
                results.append({"path": fpath, "ok": False, "error": "file too large"})
                all_ok = False
                continue
            if not is_probably_text(raw):
                results.append({"path": fpath, "ok": False, "error": "refusing to patch binary file"})
                all_ok = False
                continue
            old_content = raw.decode("utf-8", errors="replace")
        else:
            old_content = ""
        new_content, hunk_errors = _apply_hunks(old_content, file_info["hunks"])
        if hunk_errors:
            results.append({"path": fpath, "ok": False, "error": "; ".join(hunk_errors)})
            all_ok = False
            continue
        diff = _generate_diff(old_content, new_content, fpath)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(new_content, encoding="utf-8", newline="")
        except OSError as e:
            results.append({"path": fpath, "ok": False, "error": f"write failed: {e}"})
            all_ok = False
            continue
        results.append({
            "path": fpath.replace("\\", "/"),
            "ok": True,
            "action": "created" if is_new else "modified",
            "diff": diff,
        })
    summary = []
    for r in results:
        if r["ok"]:
            summary.append(f"{'A' if r['action'] == 'created' else 'M'} {r['path']}")
        else:
            summary.append(f"E {r['path']}: {r['error']}")
    return json.dumps(
        {
            "ok": all_ok,
            "files": results,
            "summary": "\n".join(summary),
        },
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_apply_patch": coding_apply_patch,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_apply_patch",
            "TOOL_DESCRIPTION": "Apply a unified diff patch to a file within the coding workspace. "
            "Patch must be in standard unified diff format (diff --git or ---/<insert> headers). "
            "Path in the patch header is resolved relative to the coding root. "
            "Useful for applying code review suggestions or generated patches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patch_text": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Full unified diff patch text (--- / +++ / @@ / +/-/ lines)",
                    },
                    "patch": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alias for patch_text",
                    },
                },
                "required": ["patch_text"],
            },
        },
    },
]
