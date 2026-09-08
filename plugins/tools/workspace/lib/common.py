"""Shared helpers for workspace tools: workspace context injection ONLY."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from plugins.tools.workspace.lib.index_lib import (
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


class ClientWorkspaceExecutionError(RuntimeError):
    """A server-side tool reached a workspace whose files live on the client (ADR 0009).

    Raised rather than returned because every workspace tool funnels through
    ``workspace_binding_from_context``, and ``run_tool`` turns the exception into the usual
    ``{"ok": false, "error": …}`` payload — one message, no per-tool plumbing.
    """


def workspace_binding_from_context(context: dict | None) -> dict[str, Any] | None:
    """Return workspace dict if ``context`` has a usable ``workspace`` with ``path`` (not ``None``).

    Raises :class:`ClientWorkspaceExecutionError` for a client-side workspace: the path belongs to
    the user's machine, so reading or writing it here would either fail confusingly or, worse, hit
    an unrelated path that happens to exist in the container.
    """
    if not context:
        return None
    ws = context.get("workspace")
    if isinstance(ws, dict):
        if str(ws.get("execution_mode") or "server").strip().lower() == "client":
            raise ClientWorkspaceExecutionError(
                f"Workspace {str(ws.get('name') or ws.get('id') or '?')!r} runs on the client: "
                "its files are on the user's machine, not on the server, so this tool cannot "
                "read or write them here (ADR 0009). The chat runtime must dispatch it over "
                "the WebSocket instead of calling the server handler."
            )
        p = ws.get("path")
        if isinstance(p, str) and p.strip():
            return ws
    return None


def workspace_record_from_context(context: dict | None) -> dict[str, Any] | None:
    """Bound workspace dict, including client-placed rows.

    Path-opening tools must keep using :func:`workspace_binding_from_context`, which raises.
    Index-query tools (semantic_search, graph, knowledge_query) only need the id.
    """
    if not context:
        return None
    ws = context.get("workspace")
    if not isinstance(ws, dict):
        return None
    wid = ws.get("id")
    if wid is None or not str(wid).strip():
        return None
    return ws


def workspace_retrieval_flags(context: dict | None) -> tuple[bool, bool]:
    """(semantic_index_enabled, retrieval_enabled) from bound workspace dict."""
    ws = workspace_record_from_context(context)
    if ws is None:
        return True, True
    return (
        bool(ws.get("semantic_index_enabled", True)),
        bool(ws.get("retrieval_enabled", True)),
    )


def workspace_id_from_context(context: dict | None) -> str | None:
    ws = workspace_record_from_context(context)
    if ws is None:
        return None
    wid = ws.get("id")
    if wid is None:
        return None
    s = str(wid).strip()
    return s or None


def workspace_docs_rag_enabled(context: dict | None) -> bool:
    ws = workspace_record_from_context(context)
    if ws is None:
        return False
    if not bool(ws.get("docs_rag_enabled", True)):
        return False
    from apps.backend.infrastructure.workspace.workspace_index_consent import (
        INDEX_CONSENT_TEXT,
        consent_covers,
        effective_index_consent,
    )

    return consent_covers(effective_index_consent(ws), INDEX_CONSENT_TEXT)


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
        from apps.backend.infrastructure.workspace.workspace_index_incremental import (
            enqueue_incremental_index_from_context,
        )

        enqueue_incremental_index_from_context(context, rel_paths)
    except Exception:
        pass