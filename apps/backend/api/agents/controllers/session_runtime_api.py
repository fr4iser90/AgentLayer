"""HTTP API: session / runtime context for the Web UI (MCP, …)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query

from apps.backend.application.platform.use_cases.platform_controller_services import config
from apps.backend.application.identity.use_cases.request_auth import get_current_user
from apps.backend.application.agent_runtime.use_cases.agent_controller_services import mcp_runtime_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/session", tags=["session"])


@router.get("/runtime")
async def get_session_runtime(
    workspace_id: str | None = Query(None, max_length=128),
    model: str | None = Query(None, max_length=512),
    model_catalog_owned_by: str | None = Query(None, max_length=64),
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
        from apps.backend.domain.workspace.resolver import resolve_db_workspace

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
    context_budget: dict[str, Any] | None = None
    mid = (model or "").strip()
    owned = (model_catalog_owned_by or "").strip() or None
    if mid:
        from apps.backend.application.agent_runtime.use_cases.agent_controller_services import (
            completion_quotas_from_budget,
            resolve_context_budget,
        )

        budget = resolve_context_budget(mid, catalog_owned_by=owned)
        if budget is not None:
            quotas = completion_quotas_from_budget(budget)
            context_budget = {
                "context_window_tokens": budget.context_window_tokens,
                "soft_limit_tokens": budget.soft_limit_tokens,
                "hard_limit_tokens": budget.hard_limit_tokens,
                "budget_source": budget.source,
                "completion_quotas": quotas.as_dict(),
            }
    return {
        "mcp": mcp,
        "context": {
            "prep_enabled": config.CHAT_CONTEXT_PREP_ENABLED,
            "budget_from": "provider_model_context_length",
            "quotas_managed_in": "apps/backend/infrastructure/context_budget.py",
            "soft_limit_ratio": config.CHAT_CONTEXT_SOFT_LIMIT_RATIO,
            "hard_limit_ratio": config.CHAT_CONTEXT_HARD_LIMIT_RATIO,
            "tools_budget_ratio": config.AGENT_TOOLS_BUDGET_RATIO,
            "tools_count_cap_ratio": config.AGENT_TOOLS_COUNT_CAP_RATIO,
            "message_max_ratio": config.CHAT_CONTEXT_MAX_MESSAGE_RATIO,
            "tool_result_max_ratio": config.CHAT_CONTEXT_TOOL_RESULT_MAX_RATIO,
            "compaction_input_ratio": config.CHAT_CONTEXT_COMPACTION_INPUT_RATIO,
            "fallback_budget_tokens": config.CHAT_CONTEXT_DEFAULT_BUDGET_TOKENS or None,
            "max_messages": config.CHAT_CONTEXT_MAX_MESSAGES,
            "compaction_enabled": config.CHAT_CONTEXT_COMPACTION_ENABLED,
            "agent_loop_trim_enabled": config.CHAT_CONTEXT_AGENT_LOOP_TRIM_ENABLED,
        },
        "context_budget": context_budget,
    }
