"""HTTP API: session / runtime context for the Web UI (MCP, …)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from apps.backend.core.config import config
from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.mcp_runtime import mcp_runtime_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/session", tags=["session"])


@router.get("/runtime")
async def get_session_runtime(
    workspace_id: str | None = Query(None, max_length=128),
    _user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    Authenticated snapshot for chat / coding headers: MCP servers, connectivity, tool counts.

    Optional ``workspace_id``: when the workspace has a non-empty ``mcp_stdio_servers`` list, status reflects
    those servers only (per-workspace MCP). Does not expose env secrets from MCP server definitions.
    """
    ws_stdio: list[Any] | None = None
    wid = (workspace_id or "").strip()
    if wid:
        from apps.backend.domain.workspace_resolver import resolve_db_workspace

        ws = resolve_db_workspace(wid, _user)
        if ws:
            raw = ws.get("mcp_stdio_servers")
            if isinstance(raw, list) and len(raw) > 0:
                ws_stdio = raw
    try:
        mcp = await mcp_runtime_status(workspace_stdio=ws_stdio)
    except Exception:
        logger.exception("session runtime: mcp_runtime_status failed")
        mcp = {"enabled": False, "import_ok": False, "agent_ids": [], "servers": [], "error": "status_failed"}
    return {
        "mcp": mcp,
        "context": {
            "prep_enabled": config.CHAT_CONTEXT_PREP_ENABLED,
            "budget_from": "provider_model_context_length",
            "soft_limit_ratio": config.CHAT_CONTEXT_SOFT_LIMIT_RATIO,
            "hard_limit_ratio": config.CHAT_CONTEXT_HARD_LIMIT_RATIO,
            "fallback_budget_tokens": config.CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS or None,
            "max_messages": config.CHAT_CONTEXT_MAX_MESSAGES,
            "compaction_enabled": config.CHAT_CONTEXT_COMPACTION_ENABLED,
            "agent_loop_trim_enabled": config.CHAT_CONTEXT_AGENT_LOOP_TRIM_ENABLED,
        },
    }
