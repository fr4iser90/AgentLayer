from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.backend.application.agent_runtime.dependencies import dashboard_db
from apps.backend.domain.shared.identity import get_identity

logger = logging.getLogger(__name__)

_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS = 8000
_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN = 200


def _dashboard_data_agent_instructions(data: Any) -> str:
    """Return trimmed instructions from ``data._agentlayer`` (optional)."""
    if not isinstance(data, dict):
        return ""
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return ""
    raw = meta.get("system_prompt_extra")
    if raw is None:
        raw = meta.get("instructions")
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    if len(s) > _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS:
        logger.warning(
            "dashboard agent instructions truncated from %d to %d chars",
            len(s),
            _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS,
        )
        return s[:_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS]
    return s


def _dashboard_data_tool_allowlist(data: Any) -> frozenset[str] | None:
    """Return allowed tool names from ``data._agentlayer.tool_allowlist`` or None if unset/empty."""
    if not isinstance(data, dict):
        return None
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("tool_allowlist")
    if raw is None:
        raw = meta.get("allowed_tools")
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
        if not parts:
            return None
        names = parts
    elif isinstance(raw, list):
        names = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
        if not names:
            return None
    else:
        return None
    if len(names) > _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN:
        logger.warning(
            "dashboard tool_allowlist truncated from %d to %d entries",
            len(names),
            _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN,
        )
        names = names[:_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN]
    return frozenset(names)


def _dashboard_tool_allowlist_from_request_context(dashboard_ctx: Any) -> frozenset[str] | None:
    if not isinstance(dashboard_ctx, dict):
        return None
    wid_s = dashboard_ctx.get("dashboard_id")
    if not isinstance(wid_s, str) or not wid_s.strip():
        return None
    try:
        wid = uuid.UUID(wid_s.strip())
    except ValueError:
        return None
    ident = get_identity()
    if ident[1] is None:
        return None
    tid, uid = ident
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return None
    return _dashboard_data_tool_allowlist(ws.get("data"))


__all__ = [
    "_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS",
    "_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN",
    "_dashboard_data_agent_instructions",
    "_dashboard_data_tool_allowlist",
    "_dashboard_tool_allowlist_from_request_context",
]
