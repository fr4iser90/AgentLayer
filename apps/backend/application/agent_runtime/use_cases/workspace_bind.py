"""Workspace bind side effects for agent tool loops."""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.backend.application.agent_runtime.dependencies import (
    build_retrieval_bootstrap_snippet,
    maybe_schedule_index_on_attach,
)

logger = logging.getLogger(__name__)


def workspace_tool_bound_workspace_id(tool_name: str, tool_result_json: str) -> str | None:
    """Return workspace id when ``bind`` / bound ``create`` succeeded."""
    if tool_name not in ("bind", "create", "workspace.bind", "workspace.create"):
        return None
    try:
        data = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None
    if tool_name in ("create", "workspace.create") and not data.get("bound"):
        return None
    ws = data.get("workspace")
    if not isinstance(ws, dict):
        return None
    wid = ws.get("id")
    if wid is None:
        return None
    s = str(wid).strip()
    return s or None


async def apply_workspace_tool_bind_side_effects(
    *,
    tool_name: str,
    result: str,
    tool_context: dict[str, Any],
    messages: list[dict[str, Any]],
    event_emit: Any,
    agent_run_id: str,
) -> None:
    """Refresh bootstrap snippet and notify UI after workspace_bind / workspace_create."""
    wid = workspace_tool_bound_workspace_id(tool_name, result)
    if not wid:
        return
    ws = tool_context.get("workspace")
    if isinstance(ws, dict):
        try:
            snippet = build_retrieval_bootstrap_snippet(ws)
            if snippet:
                messages.append({"role": "system", "content": snippet})
            maybe_schedule_index_on_attach(ws)
        except Exception as e:
            logger.debug("workspace bind bootstrap skipped: %s", e)
    if event_emit:
        await event_emit(
            {
                "type": "agent.session",
                "agent_run_id": agent_run_id,
                "workspace_id": wid,
                "workspace_bound": True,
            }
        )


def format_workspace_verify_recap(tool_result_json: str) -> str | None:
    """Build a short system snippet from ``workspace_verify`` JSON output."""
    try:
        d = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if "verify_command" not in d and "exit_code" not in d:
        return None
    parts: list[str] = ["[Workspace verify recap]"]
    cmd = d.get("verify_command")
    if isinstance(cmd, str) and cmd.strip():
        parts.append(f"command: {cmd.strip()[:400]}")
    if d.get("ok") is not None:
        parts.append(f"ok: {bool(d.get('ok'))}")
    if "exit_code" in d:
        parts.append(f"exit_code: {d.get('exit_code')}")
    out = d.get("output")
    if isinstance(out, str) and out.strip():
        sn = out.strip()
        if len(sn) > 1200:
            sn = sn[:1200] + "..."
        parts.append("output:\n" + sn)
    err = d.get("error")
    if isinstance(err, str) and err.strip() and (not isinstance(out, str) or not out.strip()):
        parts.append("error: " + err.strip()[:800])
    return "\n".join(parts)
