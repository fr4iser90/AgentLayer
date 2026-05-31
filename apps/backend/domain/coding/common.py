"""Shared helpers for coding tools: workspace context injection ONLY."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from apps.backend.domain.coding.index_lib import (
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


def workspace_retrieval_flags(context: dict | None) -> tuple[bool, bool]:
    """(semantic_index_enabled, retrieval_enabled) from bound workspace dict."""
    ws = workspace_binding_from_context(context)
    if ws is None:
        return True, True
    return (
        bool(ws.get("semantic_index_enabled", True)),
        bool(ws.get("retrieval_enabled", True)),
    )


def workspace_id_from_context(context: dict | None) -> str | None:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return None
    wid = ws.get("id")
    if wid is None:
        return None
    s = str(wid).strip()
    return s or None


def workspace_docs_rag_enabled(context: dict | None) -> bool:
    ws = workspace_binding_from_context(context)
    if ws is None:
        return False
    return bool(ws.get("docs_rag_enabled", True))


def json_workspace_missing_error() -> str:
    return json.dumps(
        {
            "ok": False,
            "error": (
                "No coding workspace bound. Call workspace_list, then workspace_create (git_url + bind) "
                "or workspace_bind before coding_* / agent_delegate. Admin users: a Git HTTPS URL in the "
                "user message may auto-create a workspace on the next chat turn."
            ),
        },
        ensure_ascii=False,
    )


_CREDENTIAL_ENV_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        ".env.test",
    }
)


def is_blocked_credential_path(rel: str) -> bool:
    """True when *rel* targets operator env files (API keys belong in user secrets)."""
    s = (rel or "").strip().replace("\\", "/")
    if not s:
        return False
    parts = [p for p in s.split("/") if p]
    base = (parts[-1] if parts else s).lower()
    if base in _CREDENTIAL_ENV_BASENAMES:
        return True
    if base.startswith(".env.") or base.endswith(".env"):
        return True
    return False


def json_blocked_credential_path_error(rel: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": (
                f"Refusing to modify credential/env file {rel!r}. "
                "Never edit docker/.env or .env for API keys or tokens."
            ),
            "hint": (
                "Use save_user_secret(service_key=<catalog key>, secret=<value>) — "
                "e.g. service_key='ssc_api_key' for SimpleSecCheck. "
                "Operator-only env vars stay in docker/.env (human/ops, not the agent)."
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


def maybe_enqueue_incremental_index(
    context: dict[str, Any] | None,
    rel_paths: list[str],
) -> None:
    """After a successful coding write, queue debounced Qdrant + Neo4j update for touched paths."""
    try:
        from apps.backend.infrastructure.workspace_index_incremental import (
            enqueue_incremental_index_from_context,
        )

        enqueue_incremental_index_from_context(context, rel_paths)
    except Exception:
        pass