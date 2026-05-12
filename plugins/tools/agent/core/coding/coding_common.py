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
    if context and "workspace" in context:
        ws = context["workspace"]
        if ws and ws.get("path"):
            return Path(ws["path"])
    return None


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