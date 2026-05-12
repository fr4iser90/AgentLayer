"""LSP (Language Server Protocol) operations for coding files.

Uses the full LSP client (coding_lsp_client.py) with proper JSON-RPC framing,
document sync, and diagnostics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from apps.backend.core.config import config

from plugins.tools.agent.core.coding.coding_lsp_client import (
    Language,
    _ext_to_language,
    _uri_to_path,
    get_manager,
)

__version__ = "2.0.0"
TOOL_ID = "coding_lsp"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "coding"
TOOL_TRIGGERS = ("coding lsp", "go to definition", "find references", "hover")
TOOL_CAPABILITIES = ("coding.lsp",)
TOOL_LABEL = "Coding: LSP"
TOOL_DESCRIPTION = (
    "LSP operations: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, "
    "diagnostics, completion, signatureHelp, rename. Supports Python, Go, Rust, TypeScript, "
    "JavaScript, Java, Ruby, PHP, C#, Dart, Elixir, Haskell, Lua, Terraform, SQL. "
    "Server auto-detected from PATH. Workspace root found via project markers (go.mod, pyproject.toml, etc.)."
)

logger = logging.getLogger(__name__)


def _path_to_uri(path: Path) -> str:
    return path.as_uri()


def _resolve_language(file_path: Path) -> Language | None:
    ext = file_path.suffix.lstrip(".")
    return _ext_to_language(ext)


def coding_lsp(arguments: dict[str, Any], context: dict | None = None) -> str:
    if not context or "workspace" not in context:
        return json.dumps({"ok": False, "error": "No workspace in context - agent must inject workspace"}, ensure_ascii=False)
    ws = context["workspace"]
    root = Path(ws["path"])

    operation = (arguments.get("operation") or "").strip()
    valid_ops = {
        "goToDefinition", "findReferences", "hover", "documentSymbol",
        "workspaceSymbol", "diagnostics", "completion", "signatureHelp", "rename",
        "status", "restart",
    }
    if operation not in valid_ops:
        return json.dumps(
            {"ok": False, "error": f"operation must be one of {sorted(valid_ops)}"},
            ensure_ascii=False,
        )

    rel = (arguments.get("path") or "").strip()
    needs_file = operation not in ("workspaceSymbol", "status", "restart")

    if needs_file and not rel:
        return json.dumps({"ok": False, "error": "path is required for this operation"}, ensure_ascii=False)

    resolved: Path | None = None
    root_hint: Path | None = None
    if rel:
        resolved = (root / rel).resolve()
        root_hint = root
        if root_hint:
            root_hint = root_hint.resolve()

    if operation == "status":
        manager = get_manager()
        return json.dumps(
            {"ok": True, "operation": "status", "servers": manager.list_servers()},
            ensure_ascii=False,
        )

    if operation == "restart":
        manager = get_manager()
        manager.shutdown_all()
        return json.dumps({"ok": True, "operation": "restart", "detail": "all LSP servers stopped"}, ensure_ascii=False)

    if operation == "workspaceSymbol":
        query = (arguments.get("query") or "").strip()
        manager = get_manager()
        first_lang = None
        if root_hint:
            for child in root_hint.rglob("*"):
                if child.is_file() and child.suffix:
                    first_lang = _resolve_language(child)
                    if first_lang:
                        break
                break
        if first_lang is None:
            first_lang = Language.PYTHON
        client = manager.get_or_create(first_lang, root_hint)
        if not client.start():
            return json.dumps(
                {"ok": False, "error": client._init_error or "LSP server not available"},
                ensure_ascii=False,
            )
        result = client.workspace_symbol(query)
        return json.dumps(result, ensure_ascii=False)

    assert resolved is not None
    uri = _path_to_uri(resolved)
    ext = resolved.suffix.lstrip(".")
    language = _resolve_language(resolved)

    if language is None:
        return json.dumps(
            {"ok": False, "error": f"unsupported file extension: {ext!r}"},
            ensure_ascii=False,
        )

    manager = get_manager()
    client = manager.get_or_create(language, root_hint)
    if not client.start():
        return json.dumps(
            {"ok": False, "error": client._init_error or "LSP server not available"},
            ensure_ascii=False,
        )

    line = max(0, int(arguments.get("line", 1)) - 1)
    character = max(0, int(arguments.get("character", 1)) - 1)
    new_name = (arguments.get("newName") or "").strip()

    if operation == "diagnostics":
        wait = arguments.get("wait", False)
        result = client.diagnostics(uri=uri, wait=bool(wait))
        return json.dumps(result, ensure_ascii=False)

    op_methods = {
        "goToDefinition": lambda: client.go_to_definition(uri, line, character),
        "findReferences": lambda: client.find_references(uri, line, character),
        "hover": lambda: client.hover(uri, line, character),
        "documentSymbol": lambda: client.document_symbol(uri),
        "completion": lambda: client.completion(uri, line, character),
        "signatureHelp": lambda: client.signature_help(uri, line, character),
        "rename": lambda: client.rename(uri, line, character, new_name),
    }

    handler = op_methods.get(operation)
    if handler is None:
        return json.dumps({"ok": False, "error": f"unknown operation: {operation}"}, ensure_ascii=False)

    result = handler()
    return json.dumps(result, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "coding_lsp": coding_lsp,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "coding_lsp",
            "TOOL_DESCRIPTION": "LSP operations: goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, "
            "diagnostics, completion, signatureHelp, rename. Supports Python, Go, Rust, TypeScript, "
            "JavaScript, Java, Ruby, PHP, C#, Dart, Elixir, Haskell, Lua, Terraform, SQL. "
            "Server auto-detected from PATH. Workspace root found via project markers (go.mod, pyproject.toml, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "goToDefinition, findReferences, hover, documentSymbol, workspaceSymbol, diagnostics, completion, signatureHelp, rename, status, restart",
                    },
                    "path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "File path relative to coding root",
                    },
                    "line": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "1-based line number",
                    },
                    "character": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "1-based character offset",
                    },
                    "query": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Search query for workspaceSymbol",
                    },
                    "newName": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "New name for rename operation",
                    },
                    "wait": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Wait for diagnostics (default false)",
                    },
                },
                "required": ["operation"],
            },
        },
    },
]
