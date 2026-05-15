"""HTTP API: session / runtime context for the Web UI (MCP, …)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from apps.backend.infrastructure.auth import get_current_user
from apps.backend.infrastructure.mcp_runtime import mcp_runtime_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/session", tags=["session"])


@router.get("/runtime")
async def get_session_runtime(_user=Depends(get_current_user)) -> dict[str, Any]:
    """
    Authenticated snapshot for chat / coding headers: MCP servers, connectivity, tool counts.

    Does not expose env secrets from MCP server definitions.
    """
    try:
        mcp = await mcp_runtime_status()
    except Exception:
        logger.exception("session runtime: mcp_runtime_status failed")
        mcp = {"enabled": False, "import_ok": False, "agent_ids": [], "servers": [], "error": "status_failed"}
    return {"mcp": mcp}
