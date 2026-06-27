"""Application service for the agent chat tool loop."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    apply_repetition_guard_to_completion,
    http_post_chat_completions,
    stream_chat_completions_aggregate,
    usage_prompt_tokens,
)
from apps.backend.application.agent_runtime.use_cases.chat_context_budget import ChatContextBudgetEnforcer
from apps.backend.application.agent_runtime.use_cases.chat_llm_transport import execute_llm_completion_round
from apps.backend.application.agent_runtime.use_cases.chat_llm_round import process_llm_tool_round
from apps.backend.application.agent_runtime.use_cases.chat_tool_events import emit_tool_done_events, emit_tool_start_event
from apps.backend.application.agent_runtime.use_cases.chat_tool_execution import execute_tool_with_agent_policy
from apps.backend.application.agent_runtime.use_cases.upload_storage_images import (
    dashboard_id_from_tool_result as _dashboard_id_from_tool_result,
    upload_pending_storage_images as _upload_pending_storage_images_sync,
)
from apps.backend.application.agent_runtime.use_cases.workspace_bind import (
    apply_workspace_tool_bind_side_effects as _apply_workspace_tool_bind_side_effects,
    format_workspace_verify_recap as _format_workspace_verify_recap,
)
from apps.backend.application.agent_runtime.runtime.io import *  # noqa: F403
from apps.backend.domain.agent_runtime.persona import _append_system_block
from apps.backend.application.agent_runtime.runtime.prompts import *  # noqa: F403
from apps.backend.application.agent_runtime.runtime.tool_loop import *  # noqa: F403
from apps.backend.domain.plugin_system.tool_routing import last_user_text
from apps.backend.domain.scheduling.run_context import record_schedule_abort, record_schedule_tool_event
from apps.backend.domain.tools.forward_policy import apply_schema_modes_to_specs

logger = logging.getLogger(__name__)


async def run_chat_tool_loop(
    *,
    messages: list[dict[str, Any]],
    tool_context: dict[str, Any],
    context_prep_meta: dict[str, Any],
    model: str | None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    plain_completion: bool,
    tools_for_request: list[Any],
    max_tool_rounds_eff: int,
    catalog_after_first_round: bool,
    tool_forward_plan: Any,
    config_tool_choice_required_retry: bool,
    stream_llm_ws: bool,
    options: dict[str, Any],
    attempts: list[tuple[str, dict[str, str], str, str]],
    llm_backend: str,
    profile_key: str,
    catalog_owned_by: str | None,
    cancel_event: Any,
    control_queue: Any,
    turn_hooks: Any,
    permission_ask: bool,
    handle_control_dict: Callable[[dict[str, Any]], bool],
    drain_control_queue: Callable[[], Awaitable[None]],
    wait_for_continue_step_after_round: Callable[[int], Awaitable[None]],
    pause_between_rounds: bool,
    tools_full_schema: bool,
    agent_id: str | None,
    workspace: dict[str, Any] | None,
    workspace_auto_created: bool,
    workspace_bound_from_conversation: bool,
    agent_auto_routed: bool,
    agent_require_workspace_verify: bool,
    model_reason: str,
    routed_category: str,
    cats: frozenset[str],
    user_id: Any,
    tenant_id: int | None,
    agent_storage_images: list[dict[str, Any]],
    is_admin: bool,
    thrash_enabled: bool,
    thrash_streak_max: int,
    doom_enabled: bool,
    doom_streak_max: int,
    run_persisted: bool,
    run_persist_warnings: list[str],
) -> dict[str, Any]:
    chosen: tuple[str, dict[str, str], str, str] | None = None
    thrash_key: str | None = None
    thrash_count = 0
    doom_key: str | None = None
    doom_count = 0
    force_no_tools_round = False
    force_no_tools_reason: str | None = None  # "thrash" | "doom"
    tools_need_full_schema: set[str] = set()

    context_budget_enforcer = ChatContextBudgetEnforcer(
        messages=messages,
        tool_context=tool_context,
        context_prep_meta=context_prep_meta,
        model=model if isinstance(model, str) else None,
        event_emit=event_emit,
        agent_run_id=agent_run_id,
    )
    enforce_agent_context_budget = context_budget_enforcer.enforce

    if not plain_completion and tools_for_request:
        messages = _append_system_block(
            messages,
            _agent_tool_budget_system_message(max_tool_rounds_eff),
        )
        await enforce_agent_context_budget(
            "before_tool_loop",
            tool_context.get("last_provider_prompt_tokens"),
        )
    for round_i in range(max_tool_rounds_eff):
        await drain_control_queue()
        if cancel_event is not None and cancel_event.is_set():
            if event_emit:
                await event_emit(
                    {
                        "type": "agent.cancelled",
                        "agent_run_id": agent_run_id,
                        "phase": "before_llm",
                        "round": round_i + 1,
                    }
                )
            raise AgentChatCancelled()

        llm_round = await process_llm_tool_round(
            messages=messages,
            tool_context=tool_context,
            context_prep_meta=context_prep_meta,
            model=model,
            event_emit=event_emit,
            agent_run_id=agent_run_id,
            plain_completion=plain_completion,
            tools_for_request=tools_for_request,
            max_tool_rounds_eff=max_tool_rounds_eff,
            catalog_after_first_round=catalog_after_first_round,
            tool_forward_plan=tool_forward_plan,
            tools_need_full_schema=tools_need_full_schema,
            round_i=round_i,
            force_no_tools_round=force_no_tools_round,
            force_no_tools_reason=force_no_tools_reason,
            config_tool_choice_required_retry=config_tool_choice_required_retry,
            stream_llm_ws=stream_llm_ws,
            options=options,
            attempts=attempts,
            llm_backend=llm_backend,
            profile_key=profile_key,
            catalog_owned_by=catalog_owned_by,
            cancel_event=cancel_event,
            turn_hooks=turn_hooks,
            enforce_agent_context_budget=enforce_agent_context_budget,
            workspace=workspace,
            agent_require_workspace_verify=agent_require_workspace_verify,
            agent_id=agent_id,
            run_persisted=run_persisted,
            run_persist_warnings=run_persist_warnings,
        )
        force_no_tools_round = llm_round.force_no_tools_round
        force_no_tools_reason = llm_round.force_no_tools_reason
        if llm_round.final_response is not None:
            return llm_round.final_response
        if llm_round.continue_round:
            continue
        data = llm_round.data or {}
        msg = llm_round.msg or {}
        choice0 = llm_round.choice0 or {}
        tool_calls = llm_round.tool_calls or []
        had_native_tool_calls = llm_round.had_native_tool_calls
        tools_for_round = llm_round.tools_for_round or []
        allowed_names = llm_round.allowed_names or set()
        model = llm_round.model or model
        attempts = llm_round.attempts or attempts
        llm_backend = llm_round.llm_backend or llm_backend

        messages.append(msg)

        batch_recap: list[str] = []
        verify_recap_line: str | None = None
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = fn.get("name") or ""
            raw_args = fn.get("arguments")
            if (
                raw_args in (None, "", "{}")
                or (isinstance(raw_args, dict) and not raw_args)
            ) and tc.get("arguments") not in (None, ""):
                raw_args = tc.get("arguments")
            args = _parse_tool_arguments(raw_args)
            alias = _rewrite_delegatable_agent_tool_alias(
                name,
                args,
                allowed_names=allowed_names,
                messages=messages,
                caller_is_admin=is_admin,
            )
            if alias:
                _alias_name, args = alias
                logger.info(
                    "tool alias rewritten round=%s %s -> delegate agent_id=%s",
                    round_i + 1,
                    name,
                    args.get("agent_id"),
                )
                name = _alias_name
            _prev_args = dict(args)
            args = _normalize_tool_call_arguments(name, args, msg, messages, tool_context)
            if args != _prev_args:
                logger.info(
                    "tool args normalized round=%s tool=%s %r -> %r",
                    round_i + 1,
                    name,
                    _prev_args,
                    args,
                )
            tool_call_id = tc.get("id") or ""
            args_line = _format_normalized_tool_args_for_recap(name, args, max_len=200)
            validation_err = validate_tool_call_arguments(name, args)
            rejected = validation_err is not None
            wire_args_preview: str | None = None
            if raw_args is not None:
                if isinstance(raw_args, str):
                    wire_args_preview = raw_args.strip()[:500] or None
                elif isinstance(raw_args, dict):
                    try:
                        wire_args_preview = json.dumps(
                            raw_args, ensure_ascii=False, sort_keys=True, default=str
                        )[:500]
                    except TypeError:
                        wire_args_preview = str(raw_args)[:500]
                else:
                    wire_args_preview = str(raw_args)[:500]
            promoted_full_schema = False
            if rejected:
                result = format_tool_call_validation_error(validation_err)
                ok_sum, err_sum = False, str(validation_err.get("message") or "invalid tool arguments")
                logger.info(
                    "tool_exec rejected run_id=%s agent=%s round=%d tool=%s empty_or_invalid args",
                    _short_run_id(agent_run_id),
                    agent_id if isinstance(agent_id, str) else "-",
                    round_i + 1,
                    name,
                )
            else:
                logger.info(
                    "tool_exec run_id=%s agent=%s round=%d tool=%s %s",
                    _short_run_id(agent_run_id),
                    agent_id if isinstance(agent_id, str) else "-",
                    round_i + 1,
                    name,
                    args_line,
                )
                if cancel_event is not None and cancel_event.is_set():
                    if event_emit:
                        await event_emit(
                            {
                                "type": "agent.cancelled",
                                "agent_run_id": agent_run_id,
                                "phase": "before_tool",
                                "round": round_i + 1,
                                "name": name,
                            }
                        )
                    raise AgentChatCancelled()
            await emit_tool_start_event(
                event_emit=event_emit,
                agent_run_id=agent_run_id,
                round_num=round_i + 1,
                name=name,
                args=args,
                args_line=args_line,
                rejected=rejected,
                wire_args_preview=wire_args_preview,
                validation_err=validation_err if isinstance(validation_err, dict) else None,
            )
            if not rejected:
                result = await execute_tool_with_agent_policy(
                    name=name,
                    args=args,
                    messages=messages,
                    tool_context=tool_context,
                    permission_ask=permission_ask,
                    control_queue=control_queue,
                    cancel_event=cancel_event,
                    event_emit=event_emit,
                    agent_run_id=agent_run_id,
                    round_i=round_i,
                    handle_control_dict=handle_control_dict,
                )
                ok_sum, err_sum = _tool_result_summary(result)
            if (
                str(name).strip()
                and tool_call_warrants_full_schema_promotion(
                    rejected=rejected,
                    wire_args=_prev_args,
                    normalized_args=args,
                    result_ok=ok_sum,
                    result_error=err_sum if not ok_sum else None,
                )
            ):
                tools_need_full_schema.add(str(name).strip())
                promoted_full_schema = True
                logger.info(
                    "tool full schema promoted for next round run_id=%s tool=%s rejected=%s",
                    _short_run_id(agent_run_id),
                    name,
                    rejected,
                )
            if (
                name == "git_read"
                and ok_sum
                and str(
                    tool_context.get("agent_delegate_mode")
                    or tool_context.get("agent_plan_delegate_mode")
                    or ""
                ).strip().lower()
                == "git_forensics"
            ):
                op = str(args.get("operation") or args.get("subcommand") or "").strip().lower()
                if op in ("diff_stat", "diff-stat", "diff"):
                    tool_context["plan_git_diff_seen"] = True
            follow_hint = (
                None
                if name in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL
                else _tool_result_followup_hint(name, result)
            )
            if follow_hint:
                messages.append({"role": "system", "content": follow_hint[:2500]})
            if ok_sum:
                from apps.backend.domain.delegation.enforcement import (
                    extract_artifact_ids_from_tool_result,
                    extract_handoff_artifact_ids,
                    record_orchestrator_delegate_success,
                )

                coll = tool_context.get("handoff_artifact_collector")
                if isinstance(coll, list):
                    for aid in extract_artifact_ids_from_tool_result(result or ""):
                        if aid and aid not in coll:
                            coll.append(aid)
                if str(tool_context.get("agent_id") or "") == "general":
                    if name == "delegate" and ok_sum:
                        record_orchestrator_delegate_success(tool_context, args, result or "")
                        sub_aid = str(args.get("agent_id") or "").strip()
                        refs = args.get("artifact_refs")
                        if sub_aid == "coding" and isinstance(refs, list) and refs:
                            tool_context.pop("orchestrator_pending_artifact_refs", None)
                    else:
                        pending = extract_handoff_artifact_ids(result or "")
                        if pending:
                            tool_context["orchestrator_pending_artifact_refs"] = pending
            record_schedule_tool_event(
                round_num=round_i + 1,
                tool_name=name,
                args=args,
                ok=ok_sum,
                error=err_sum if not ok_sum else None,
            )
            if name == "workspace_verify":
                try:
                    _vd = json.loads(result)
                    if isinstance(_vd, dict) and _vd.get("ok") is True:
                        tool_context["workspace_verify_succeeded"] = True
                except Exception:
                    pass
                vr = _format_workspace_verify_recap(result)
                if vr:
                    verify_recap_line = vr
            dash_id = _dashboard_id_from_tool_result(result)
            if not dash_id and args.get("dashboard_id"):
                dash_id = str(args.get("dashboard_id") or "").strip() or None
            storage_upload_event: dict[str, Any] | None = None
            if (
                dash_id
                and ok_sum is not False
                and agent_storage_images
                and isinstance(user_id, uuid.UUID)
                and tenant_id is not None
            ):
                storage_upload = await asyncio.to_thread(
                    _upload_pending_storage_images_sync,
                    tool_context=tool_context,
                    user_id=user_id,
                    tenant_id=int(tenant_id),
                    dashboard_id=dash_id,
                )
                if int(storage_upload.get("uploaded") or 0) > 0 or storage_upload.get("errors"):
                    storage_upload_event = {
                        "type": "agent.tool_done",
                        "agent_run_id": agent_run_id,
                        "round": round_i + 1,
                        "name": "dashboard.upload_photos",
                        "result_ok": bool(storage_upload.get("ok")),
                        "result_chars": int(storage_upload.get("uploaded") or 0),
                        "dashboard_id": dash_id,
                        "result_display": (
                            f"uploaded {int(storage_upload.get('uploaded') or 0)} image(s)"
                        ),
                    }
                    if storage_upload.get("errors"):
                        storage_upload_event["result_error"] = "; ".join(
                            str(x) for x in list(storage_upload.get("errors") or [])[:3]
                        )[:500]
            if event_emit:
                await _apply_workspace_tool_bind_side_effects(
                    tool_name=name,
                    result=result or "",
                    tool_context=tool_context,
                    messages=messages,
                    event_emit=event_emit,
                    agent_run_id=agent_run_id,
                )
            if thrash_enabled:
                nk, nc, thr_hint, force_next = _agent_tool_thrash_tick(
                    thrash_key,
                    thrash_count,
                    tool_name=name,
                    ok_r=ok_sum,
                    err_r=err_sum,
                    max_streak=thrash_streak_max,
                )
                thrash_key, thrash_count = nk, nc
                if thr_hint:
                    messages.append({"role": "system", "content": thr_hint})
                if force_next:
                    force_no_tools_round = True
                    force_no_tools_reason = "thrash"
                    logger.info(
                        "tool loop guard: thrash streak reached for tool=%r — next LLM round will omit tools[]",
                        name,
                    )
            if doom_enabled:
                dk, dc, doom_hint = _agent_tool_doom_loop_tick(
                    doom_key,
                    doom_count,
                    tool_name=name,
                    args=args,
                    max_streak=doom_streak_max,
                    exclude_names=config.AGENT_TOOL_DOOM_LOOP_EXCLUDE,
                )
                doom_key, doom_count = dk, dc
                if doom_hint:
                    messages.append({"role": "system", "content": doom_hint})
                    force_no_tools_round = True
                    force_no_tools_reason = "doom"
                    try:
                        _args_preview = json.dumps(dict(args), sort_keys=True, separators=(",", ":"), default=str)
                    except TypeError:
                        _args_preview = str(args)
                    if len(_args_preview) > 400:
                        _args_preview = _args_preview[:400] + "…"
                    logger.info(
                        "tool loop guard: doom-loop streak reached (tool=%r args=%s max_streak=%d) — "
                        "next LLM round will omit tools[]",
                        name,
                        _args_preview,
                        doom_streak_max,
                    )
                    if tool_context.get("agent_unattended"):
                        record_schedule_abort("repeated_tool_loop")
            await emit_tool_done_events(
                event_emit=event_emit,
                agent_run_id=agent_run_id,
                round_num=round_i + 1,
                name=name,
                result=result,
                ok_sum=ok_sum,
                err_sum=err_sum,
                dash_id=dash_id,
                promoted_full_schema=promoted_full_schema,
                turn_hooks=turn_hooks,
                tool_context=tool_context,
                storage_upload_event=storage_upload_event,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                }
            )
            recovery = _http_error_recovery_hint(name, result)
            if recovery:
                messages.append({"role": "system", "content": recovery})
            param_recovery = (
                None
                if name in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL
                else _tool_parameter_recovery_hint(name, result or "")
            )
            if param_recovery:
                messages.append({"role": "system", "content": param_recovery})
            st = "ok" if ok_sum is True else ("err" if ok_sum is False else "?")
            batch_recap.append(f"{name}:{st}")

        if config.AGENT_SESSION_TOOL_RECAP_ENABLED and batch_recap:
            cap = config.AGENT_SESSION_TOOL_RECAP_MAX
            parts = batch_recap[:cap]
            tail = f" (+{len(batch_recap) - cap} more)" if len(batch_recap) > cap else ""
            recap_line = _agent_session_tool_recap_system_message(
                parts,
                overflow_tail=tail,
                user_task=last_user_text(messages),
            )
            messages.append({"role": "system", "content": recap_line[:900]})

        if verify_recap_line:
            messages.append({"role": "system", "content": verify_recap_line[:2500]})

        await enforce_agent_context_budget(
            f"round_{round_i + 1}_post_tools",
            tool_context.get("last_provider_prompt_tokens"),
            round_num=round_i + 1,
        )

        if (
            pause_between_rounds
            and control_queue is not None
            and round_i + 1 < max_tool_rounds_eff
        ):
            await wait_for_continue_step_after_round(round_i + 1)



__all__ = ["run_chat_tool_loop"]
