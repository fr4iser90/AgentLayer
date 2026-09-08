"""ADR 0009 milestone 2: dispatch workspace-path tools to a connected client."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled
from apps.backend.domain.agent_runtime.tool_catalog import _tool_spec_name
from apps.backend.infrastructure.agent_runtime.context_budget import tool_result_max_chars_for_budget
from apps.backend.infrastructure.workspace.workspace_execution import is_client_execution

logger = logging.getLogger(__name__)

# LLM-visible names that open ``context["workspace"]["path"]`` on the server.
# Index *query* tools (semantic_search, graph, retrieve_context, knowledge_query) stay
# on the server: they key off workspace_id, not the laptop path.
CLIENT_PATH_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "list_dir",
        "glob",
        "search",
        "apply_patch",
        "edit",
        "replace",
        "bash",
        "git_sync",
        "symbols",
        "index",
        "knowledge_index",
        "lsp",
        "workspace_verify",
    }
)

# Workspace CRUD stays on the server even for a client-placed row.
SERVER_SIDE_WORKSPACE_TOOLS = frozenset({"list", "create", "bind"})

DEFAULT_CLIENT_TOOL_TIMEOUT_SEC = 90
_FALLBACK_RESULT_MAX_CHARS = 80_000
_UNSUPPORTED = json.dumps({"ok": False, "error": "unsupported"}, ensure_ascii=False)


def advertised_workspace_tools(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, (set, frozenset)):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    if isinstance(raw, list):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return frozenset()


def workspace_is_client(tool_context: dict[str, Any] | None) -> bool:
    if not isinstance(tool_context, dict):
        return False
    ws = tool_context.get("workspace")
    if not isinstance(ws, dict):
        return False
    return is_client_execution(ws.get("execution_mode"))


def filter_tools_for_client_workspace(
    tools_for_request: list[Any],
    advertised: frozenset[str],
) -> list[Any]:
    """Drop path-consuming tools the client did not advertise; keep CRUD and the rest."""
    kept: list[Any] = []
    for spec in tools_for_request:
        name = _tool_spec_name(spec)
        if name is None:
            kept.append(spec)
            continue
        if name in SERVER_SIDE_WORKSPACE_TOOLS:
            kept.append(spec)
            continue
        if name in CLIENT_PATH_TOOLS:
            if name in advertised:
                kept.append(spec)
            continue
        kept.append(spec)
    return kept


def cap_client_tool_result(text: str, *, max_chars: int | None) -> str:
    limit = int(max_chars) if isinstance(max_chars, int) and max_chars > 0 else _FALLBACK_RESULT_MAX_CHARS
    if len(text) <= limit:
        return text
    keep = max(500, limit - 80)
    return text[:keep] + "\n\n…[truncated by server for context budget]"


def result_max_chars(tool_context: dict[str, Any] | None) -> int:
    budget = None
    if isinstance(tool_context, dict):
        budget = tool_context.get("_context_budget")
    capped = tool_result_max_chars_for_budget(budget)
    return int(capped) if isinstance(capped, int) and capped > 0 else _FALLBACK_RESULT_MAX_CHARS


def timeout_for_tool(name: str, args: dict[str, Any]) -> float:
    slack = 15.0
    if name == "bash":
        try:
            requested = int(args.get("timeout") or 60)
        except (TypeError, ValueError):
            requested = 60
        return float(min(180, max(5, requested))) + slack
    if name == "git_sync":
        return 120.0 + slack
    return float(DEFAULT_CLIENT_TOOL_TIMEOUT_SEC)


async def _next_control_message(
    control_queue: asyncio.Queue,
    cancel_event: asyncio.Event | None,
    timeout: float,
) -> dict[str, Any] | None:
    """Wait for a queue item, a cancel, or a timeout. ``None`` means timeout."""
    queue_task = asyncio.create_task(control_queue.get())
    tasks: list[asyncio.Task[Any]] = [queue_task]
    cancel_task: asyncio.Task[Any] | None = None
    if cancel_event is not None:
        cancel_task = asyncio.create_task(cancel_event.wait())
        tasks.append(cancel_task)
    done, pending = await asyncio.wait(
        tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if cancel_event is not None and cancel_event.is_set():
        raise AgentChatCancelled()
    if not done:
        return None
    finished = next(iter(done))
    if cancel_task is not None and finished is cancel_task:
        raise AgentChatCancelled()
    msg = finished.result()
    return msg if isinstance(msg, dict) else None


def _payload_from_tool_result(m: dict[str, Any], *, max_chars: int) -> str:
    if m.get("ok") is False:
        err = m.get("error")
        text = str(err).strip() if err is not None else "client tool failed"
        return json.dumps({"ok": False, "error": text[:4000]}, ensure_ascii=False)
    raw = m.get("result")
    if raw is None:
        return json.dumps({"ok": True}, ensure_ascii=False)
    if isinstance(raw, str):
        return cap_client_tool_result(raw, max_chars=max_chars)
    try:
        dumped = json.dumps(raw, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        dumped = str(raw)
    return cap_client_tool_result(dumped, max_chars=max_chars)


async def wait_for_client_tool_result(
    *,
    control_queue: asyncio.Queue,
    cancel_event: asyncio.Event | None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    request_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    round_i: int,
    handle_control: Callable[[dict[str, Any]], bool],
    timeout_sec: float,
    max_chars: int,
) -> str:
    if event_emit:
        await event_emit(
            {
                "type": "agent.tool_invoke",
                "agent_run_id": agent_run_id,
                "request_id": request_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "round": round_i + 1,
            }
        )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(1.0, float(timeout_sec))
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"client tool timed out after {int(timeout_sec)}s",
                },
                ensure_ascii=False,
            )
        m = await _next_control_message(control_queue, cancel_event, remaining)
        if m is None:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"client tool timed out after {int(timeout_sec)}s",
                },
                ensure_ascii=False,
            )
        typ = m.get("type")
        if typ == "tool_result":
            if str(m.get("request_id") or "") != request_id:
                logger.debug("discarding tool_result (stale request_id)")
                continue
            return _payload_from_tool_result(m, max_chars=max_chars)
        if typ == "permission_reply":
            logger.debug("discarding permission_reply while waiting for tool_result")
            continue
        if handle_control(m):
            raise AgentChatCancelled()
        if cancel_event is not None and cancel_event.is_set():
            raise AgentChatCancelled()


async def dispatch_client_workspace_tool(
    *,
    name: str,
    args: dict[str, Any],
    tool_context: dict[str, Any],
    control_queue: Any,
    cancel_event: Any,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    round_i: int,
    handle_control_dict: Callable[[dict[str, Any]], bool],
) -> str:
    advertised = advertised_workspace_tools(tool_context.get("client_workspace_tools"))
    if name not in advertised:
        return _UNSUPPORTED
    if control_queue is None:
        return json.dumps(
            {
                "ok": False,
                "error": (
                    "This workspace runs on the client, but there is no live control channel "
                    "to dispatch the tool (nested/unattended runs cannot reach the laptop)."
                ),
            },
            ensure_ascii=False,
        )
    rid = str(uuid.uuid4())
    return await wait_for_client_tool_result(
        control_queue=control_queue,
        cancel_event=cancel_event,
        event_emit=event_emit,
        agent_run_id=agent_run_id,
        request_id=rid,
        tool_name=name,
        arguments=dict(args or {}),
        round_i=round_i,
        handle_control=handle_control_dict,
        timeout_sec=timeout_for_tool(name, args or {}),
        max_chars=result_max_chars(tool_context),
    )


__all__ = [
    "CLIENT_PATH_TOOLS",
    "SERVER_SIDE_WORKSPACE_TOOLS",
    "advertised_workspace_tools",
    "cap_client_tool_result",
    "dispatch_client_workspace_tool",
    "filter_tools_for_client_workspace",
    "wait_for_client_tool_result",
    "workspace_is_client",
]
