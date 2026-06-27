from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.application.agent_runtime.runtime.prompts import AgentChatCancelled, _wait_for_tool_permission_reply
from apps.backend.application.agent_runtime.runtime.tool_loop import _CODING_TOOLS_PERMISSION_ASK, _thread_with_cancel
from apps.backend.domain.tools.executor import execute_tool
from apps.backend.domain.tools.invocation_context import (
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)

logger = logging.getLogger(__name__)


async def execute_tool_with_agent_policy(
    *,
    name: str,
    args: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_context: dict[str, Any],
    permission_ask: bool,
    control_queue: Any,
    cancel_event: Any,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    round_i: int,
    handle_control_dict: Callable[[dict[str, Any]], bool],
) -> str:
    from apps.backend.domain.delegation.enforcement import (
        coding_delegate_tool_blocked,
        orchestrator_pre_tool_blocked,
    )

    policy_block = orchestrator_pre_tool_blocked(name, args, tool_context)
    if policy_block is None:
        policy_block = coding_delegate_tool_blocked(name, args, tool_context)
    if (
        policy_block is None
        and name == "artifact_get"
        and isinstance(tool_context.get("agent_storage_images_pending"), list)
    ):
        policy_block = (
            "This turn has server-side image uploads. Do not call artifact_get for them; "
            "create/select a dashboard gallery and the backend will upload the images."
        )
    if policy_block:
        return json.dumps({"ok": False, "error": policy_block}, ensure_ascii=False)

    tctx = set_tool_invocation_messages(list(messages))
    try:
        perm_always = tool_context.get("permission_always_allow_tools")
        if not isinstance(perm_always, set):
            perm_always = set()
            tool_context["permission_always_allow_tools"] = perm_always
        need_gate = (
            permission_ask
            and not bool(tool_context.get("agent_unattended"))
            and bool(tool_context.get("agent_coding_tools_permission_ask"))
            and name in _CODING_TOOLS_PERMISSION_ASK
            and name not in perm_always
        )
        if need_gate and control_queue is None:
            logger.warning(
                "agent_permission_ask set but no control_queue; executing %s without approval",
                name,
            )
        if need_gate and control_queue is not None:
            preview = json.dumps(args, ensure_ascii=False, default=str)[:2000]
            rid = str(uuid.uuid4())
            rep, fb_msg = await _wait_for_tool_permission_reply(
                control_queue=control_queue,
                cancel_event=cancel_event,
                event_emit=event_emit,
                agent_run_id=agent_run_id,
                request_id=rid,
                tool_name=name,
                args_preview=preview,
                round_i=round_i,
                handle_control=handle_control_dict,
            )
            if rep == "reject":
                rej: dict[str, Any] = {
                    "ok": False,
                    "error": "User rejected permission for this tool call.",
                }
                if fb_msg:
                    rej["user_message"] = fb_msg
                return json.dumps(rej, ensure_ascii=False)
            if rep == "always":
                perm_always.add(name)
        return await _thread_with_cancel(
            cancel_event,
            execute_tool,
            name,
            args,
            context=tool_context,
        )
    except AgentChatCancelled:
        raise
    finally:
        reset_tool_invocation_messages(tctx)


__all__ = ["execute_tool_with_agent_policy"]
