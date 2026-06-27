from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from apps.backend.application.agent_runtime.use_cases.media_events import media_play_websocket_event
from apps.backend.application.agent_runtime.runtime.tool_loop import _emit_secret_prompt_from_tool_result
from apps.backend.domain.plugin_system.registry import get_registry


async def emit_tool_start_event(
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    round_num: int,
    name: str,
    args: dict[str, Any],
    args_line: str,
    rejected: bool,
    wire_args_preview: str | None,
    validation_err: dict[str, Any] | None,
) -> None:
    if event_emit is None:
        return
    from apps.backend.domain.tools.step_label import format_tool_step_label_from_args

    tool_label: str | None = None
    try:
        tool_label = get_registry().display_label_for_tool(name)
    except Exception:
        tool_label = None
    step_label = format_tool_step_label_from_args(name, args, tool_label=tool_label)
    ev: dict[str, Any] = {
        "type": "agent.tool_start",
        "agent_run_id": agent_run_id,
        "round": round_num,
        "name": name,
        "summary": args_line if not rejected else "rejected: empty or invalid arguments",
        "step_label": step_label,
        "rejected": rejected,
    }
    if wire_args_preview is not None:
        ev["wire_arguments"] = wire_args_preview
    if args:
        ev["normalized_arguments"] = dict(args)
    if rejected and isinstance(validation_err, dict):
        ev["validation"] = {
            k: validation_err.get(k)
            for k in (
                "missing_or_empty",
                "schema_required",
                "any_of_required",
                "received_arguments",
            )
            if validation_err.get(k) is not None
        }
    if tool_label:
        ev["label"] = tool_label
    await event_emit(ev)


async def emit_tool_done_events(
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    round_num: int,
    name: str,
    result: str | None,
    ok_sum: bool | None,
    err_sum: str | None,
    dash_id: str | None,
    promoted_full_schema: bool,
    turn_hooks: Any,
    tool_context: dict[str, Any],
    storage_upload_event: dict[str, Any] | None,
) -> None:
    if event_emit is None:
        return
    await _emit_secret_prompt_from_tool_result(
        name,
        result,
        event_emit=event_emit,
        agent_run_id=agent_run_id,
    )
    ev_done: dict[str, Any] = {
        "type": "agent.tool_done",
        "agent_run_id": agent_run_id,
        "round": round_num,
        "name": name,
        "result_chars": len(result or ""),
    }
    if ok_sum is not None:
        ev_done["result_ok"] = ok_sum
    if err_sum:
        ev_done["result_error"] = err_sum[:500]
    from apps.backend.domain.delegation.enforcement import tool_result_display_line

    display = tool_result_display_line(name, result or "")
    if display:
        ev_done["result_display"] = display
    if dash_id:
        ev_done["dashboard_id"] = dash_id
    if promoted_full_schema:
        ev_done["promoted_full_schema"] = True
    hook_extras = turn_hooks.on_tool_done(
        tool_context,
        name=name,
        result=result or "",
        ok_sum=ok_sum,
    )
    if hook_extras:
        ev_done.update(hook_extras)
    media_ev = media_play_websocket_event(name, result)
    if media_ev:
        ev_done["media_play"] = {k: v for k, v in media_ev.items() if k != "type"}
    await event_emit(ev_done)
    if storage_upload_event:
        await event_emit(storage_upload_event)
    if media_ev:
        await event_emit(media_ev)


__all__ = ["emit_tool_done_events", "emit_tool_start_event"]
