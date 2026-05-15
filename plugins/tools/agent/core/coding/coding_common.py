"""Shared helpers for coding tools: workspace context injection ONLY."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from plugins.tools.agent.core.coding.coding_index_lib import (
        _HAS_TS,
        _SUPPORTED_LANGUAGES,
    )
except ImportError:
    _HAS_TS = False
    _SUPPORTED_LANGUAGES = {}


def get_workspace_from_context(context: dict | None = None) -> Path | None:
    """Get workspace path from context - the CORRECT way."""
    ws = workspace_binding_from_context(context)
    if ws is None:
        return None
    return Path(ws["path"])


def workspace_binding_from_context(context: dict | None) -> dict[str, Any] | None:
    """Return workspace dict if ``context`` has a usable ``workspace`` with ``path`` (not ``None``)."""
    if not context:
        return None
    ws = context.get("workspace")
    if isinstance(ws, dict):
        p = ws.get("path")
        if isinstance(p, str) and p.strip():
            return ws
    return None


def json_workspace_missing_error() -> str:
    return json.dumps(
        {
            "ok": False,
            "error": (
                "No coding workspace bound. Select a workspace in the UI (workspace_id on the request), "
                "or send a Git HTTPS URL as an admin user to auto-create a cloned workspace for this chat."
            ),
        },
        ensure_ascii=False,
    )


def require_workspace(context: dict | None = None) -> Path:
    """Get workspace path or raise clear error - NO FALLBACKS!"""
    if not context:
        raise ValueError("No context provided - tool must receive context from agent!")
    
    path = get_workspace_from_context(context)
    if not path:
        raise ValueError("No workspace in context - agent must inject workspace before calling tools!")
    
    return path


def is_probably_text(data: bytes) -> bool:
    if not data:
        return True
    return b"\x00" not in data[:8192]


def coalesce_content(arguments: dict[str, Any]) -> tuple[str, str | None]:
    """Extract *content* from arguments, trying ``content``, ``text``, ``source`` keys."""
    for key in ("content", "text", "source"):
        v = arguments.get(key)
        if v is not None:
            s = str(v)
            return s, None
    return "", "content is required (use 'content', 'text', or 'source' key)"