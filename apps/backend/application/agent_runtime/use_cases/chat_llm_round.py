"""Single LLM round processing for agent chat tool loops."""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    apply_repetition_guard_to_completion,
    http_post_chat_completions,
    stream_chat_completions_aggregate,
    usage_prompt_tokens,
)
from apps.backend.application.agent_runtime.use_cases.chat_llm_transport import execute_llm_completion_round
from apps.backend.application.agent_runtime.runtime.io import *  # noqa: F403
from apps.backend.application.agent_runtime.runtime.prompts import *  # noqa: F403
from apps.backend.application.agent_runtime.runtime.tool_loop import *  # noqa: F403
from apps.backend.domain.agent_runtime.persona import _append_system_block
from apps.backend.domain.tools.forward_policy import apply_schema_modes_to_specs

logger = logging.getLogger(__name__)


@dataclass
class LlmToolRoundResult:
    final_response: dict[str, Any] | None = None
    continue_round: bool = False
    data: dict[str, Any] | None = None
    msg: dict[str, Any] | None = None
    choice0: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    had_native_tool_calls: bool = False
    tools_for_round: list[Any] | None = None
    allowed_names: set[str] | frozenset[str] | None = None
    model: str | None = None
    attempts: list[tuple[str, dict[str, str], str, str]] | None = None
    llm_backend: str | None = None
    force_no_tools_round: bool = False
    force_no_tools_reason: str | None = None


async def process_llm_tool_round(
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
    tools_need_full_schema: set[str],
    round_i: int,
    force_no_tools_round: bool,
    force_no_tools_reason: str | None,
    config_tool_choice_required_retry: bool,
    stream_llm_ws: bool,
    options: dict[str, Any],
    attempts: list[tuple[str, dict[str, str], str, str]],
    llm_backend: str,
    profile_key: str,
    catalog_owned_by: str | None,
    cancel_event: Any,
    turn_hooks: Any,
    enforce_agent_context_budget: Callable[..., Awaitable[None]],
    workspace: dict[str, Any] | None,
    agent_require_workspace_verify: bool,
    agent_id: str | None,
    run_persisted: bool,
    run_persist_warnings: list[str],
) -> LlmToolRoundResult:
    round_full_schema_tools: list[str] = []
    if force_no_tools_round:
        _guard_reason = force_no_tools_reason or "thrash"
        logger.info(
            "chat tool loop round %d/%d: forwarding 0 tools (reason=loop_guard_%s)",
            round_i + 1,
            max_tool_rounds_eff,
            _guard_reason,
        )
        tools_for_round = []
        if force_no_tools_reason == "doom":
            messages.append({"role": "system", "content": _AGENT_TOOL_DOOM_FORCE_TEXT})
        else:
            messages.append({"role": "system", "content": _AGENT_TOOL_THRASH_FORCE_TEXT})
        force_no_tools_round = False
        force_no_tools_reason = None
    else:
        tools_for_round = list(tools_for_request)
        use_catalog = round_i > 0 and catalog_after_first_round
        if use_catalog or tools_need_full_schema:
            schema_modes: dict[str, str] = (
                {
                    n: "catalog"
                    for spec in tool_forward_plan.forward_specs
                    if isinstance(spec, dict)
                    and isinstance(spec.get("function"), dict)
                    and (n := str(spec["function"].get("name") or "").strip())
                }
                if use_catalog
                else dict(tool_forward_plan.schema_mode_per_tool)
            )
            for promoted in tools_need_full_schema:
                if promoted:
                    schema_modes[promoted] = "full"
            round_full_schema_tools = sorted(
                n for n, mode in schema_modes.items() if mode == "full"
            )
            if schema_modes:
                tools_for_round = apply_schema_modes_to_specs(
                    tool_forward_plan.forward_specs,
                    schema_modes,
                    default_full_schema=False,
                )
        if max_tool_rounds_eff >= 3 and round_i == max_tool_rounds_eff - 2:
            messages.append(
                {
                    "role": "system",
                    "content": _agent_near_max_tool_rounds_reminder(
                        round_i + 1, max_tool_rounds_eff
                    ),
                }
            )
        if max_tool_rounds_eff >= 2 and round_i == max_tool_rounds_eff - 1:
            tools_for_round = []
            recap_blob = _build_client_tool_context_markdown(messages)
            cap = 10_000
            if recap_blob.strip():
                if len(recap_blob) > cap:
                    recap_blob = recap_blob[:cap] + "\n\n…[truncated]"
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Below is **server-extracted** context for this reply: (1) each LLM tool "
                            "round — which tools were **requested** and with which (normalized) arguments; "
                            "(2) each tool **result** payload. Your final answer **must** be consistent "
                            "with this material (do not invent file paths or outcomes not supported there).\n\n"
                            + recap_blob
                        ),
                    }
                )
            messages.append(
                {
                    "role": "system",
                    "content": _agent_final_round_text_only_hint(
                        round_i + 1, max_tool_rounds_eff
                    ),
                }
            )
            logger.info(
                "chat tool loop round %d/%d: forwarding 0 tools (reason=final_round_text_only_policy)",
                round_i + 1,
                max_tool_rounds_eff,
            )
    allowed_names = _names_from_tool_list(tools_for_round)

    await enforce_agent_context_budget(
        f"round_{round_i + 1}_pre_llm",
        tool_context.get("last_provider_prompt_tokens"),
        round_num=round_i + 1,
    )

    if event_emit:
        _llm_start: dict[str, Any] = {
            "type": "agent.llm_round_start",
            "agent_run_id": agent_run_id,
            "round": round_i + 1,
            "max_rounds": max_tool_rounds_eff,
            "forwarded_tool_names": [
                n for t in tools_for_round if (n := _tool_spec_name(t)) is not None
            ],
        }
        if round_full_schema_tools:
            _llm_start["full_schema_tools"] = list(round_full_schema_tools)
        await event_emit(_llm_start)

    use_llm_stream = bool(stream_llm_ws and event_emit is not None)
    round_no = round_i + 1

    async def _emit_llm_token_delta(s: str) -> None:
        if not s or event_emit is None:
            return
        await event_emit(
            {
                "type": "agent.llm_delta",
                "agent_run_id": agent_run_id,
                "round": round_no,
                "delta": s,
            }
        )

    async def _emit_llm_reasoning_delta(s: str) -> None:
        if not s or event_emit is None:
            return
        await event_emit(
            {
                "type": "agent.llm_delta",
                "agent_run_id": agent_run_id,
                "round": round_no,
                "channel": "reasoning",
                "reasoning_delta": s,
            }
        )

    payload_base: dict[str, Any] = {
        "messages": messages,
        "stream": False,
        **options,
    }
    if use_llm_stream:
        so = payload_base.get("stream_options")
        if not isinstance(so, dict):
            payload_base["stream_options"] = {"include_usage": True}
        elif so.get("include_usage") is not True:
            payload_base["stream_options"] = {**so, "include_usage": True}
    if tools_for_round:
        payload_base["tools"] = tools_for_round
        turn_hooks.apply_payload_tool_choice(
            payload_base,
            tool_context,
            allowed_names=allowed_names,
            round_i=round_i,
            max_rounds=max_tool_rounds_eff,
        )

    llm_round = await execute_llm_completion_round(
        attempts=attempts,
        payload_base=payload_base,
        llm_backend=llm_backend,
        profile_key=profile_key,
        use_llm_stream=use_llm_stream,
        cancel_event=cancel_event,
        on_text_delta=_emit_llm_token_delta,
        on_reasoning_delta=_emit_llm_reasoning_delta,
        catalog_owned_by=catalog_owned_by,
    )
    data = llm_round.data
    tools_omitted = llm_round.tools_omitted
    chosen = llm_round.chosen
    model = llm_round.model
    attempts = llm_round.attempts
    llm_backend = llm_round.llm_backend

    if tools_omitted:
        tools_for_round = []
        allowed_names = set()
        logger.warning(
            "chat tool loop round %d/%d: provider returned tools_omitted=True — treating this completion "
            "as text-only (no tools[] forwarded to model for this response)",
            round_i + 1,
            max_tool_rounds_eff,
        )

    apply_repetition_guard_to_completion(data)

    choice0, msg, tool_calls, had_native_tool_calls = (
        _extract_tool_calls_from_completion_response(
            data,
            allowed_tool_names=allowed_names,
        )
    )

    if not tool_calls and tools_for_round:
        recovered = turn_hooks.recover_tool_calls_from_message(
            msg,
            allowed_tool_names=allowed_names,
            tools_for_round=tools_for_round,
        )
        if recovered:
            from apps.backend.domain.agent_runtime.assistant_display import (
                sanitize_assistant_display_text,
            )

            tool_calls = recovered
            had_native_tool_calls = False
            msg = dict(msg)
            msg["tool_calls"] = recovered
            raw_c = msg.get("content")
            if isinstance(raw_c, str):
                msg["content"] = sanitize_assistant_display_text(raw_c) or ""
            choice0 = dict(choice0)
            choice0["message"] = msg
            ch_list = data.get("choices")
            if isinstance(ch_list, list) and ch_list and isinstance(ch_list[0], dict):
                ch_list[0] = choice0
            logger.info(
                "agent turn hook: recovered tool_call(s) from assistant text (round %d)",
                round_i + 1,
            )

    # Some models return only assistant text (TEXT_NO_TOOLS) even when tools[] is present.
    # OpenAI-compatible: retry once with tool_choice=required so the backend emits tool_calls.
    # Only on the first planner round: later rounds may legitimately return final text; forcing
    # tool_choice here would pick a random tool (e.g. register_secrets) and thrash the chat.
    if (
        round_i == 0
        and not tool_calls
        and tools_for_round
        and not plain_completion
        and not tools_omitted
        and config_tool_choice_required_retry
    ):
        payload_retry = dict(payload_base)
        payload_retry["model"] = chosen[2]
        payload_retry["tool_choice"] = "required"
        try:
            if use_llm_stream:
                data_r, tools_omitted_r, chosen_r = await stream_chat_completions_aggregate(
                    attempts,
                    dict(payload_retry),
                    llm_backend=llm_backend,
                    profile_key=profile_key,
                    on_text_delta=_emit_llm_token_delta,
                    cancel_event=cancel_event,
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
                )
                chosen = chosen_r
                model = chosen[2]
            else:
                data_r, tools_omitted_r = await _thread_with_cancel(
                    cancel_event,
                    http_post_chat_completions,
                    chosen[0],
                    payload_retry,
                    headers=chosen[1],
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
                )
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 422):
                logger.warning(
                    "Local provider rejected tool_choice=required (status=%s); keeping first completion. body~=%s",
                    e.response.status_code,
                    _redact_provider_error_text_for_log(e.response.text, max_len=320),
                )
            else:
                err_body = _redact_provider_error_text_for_log(
                    e.response.text, max_len=600
                )
                logger.error(
                    "LLM chat/completions retry failed (%s): status=%s llm_model_id=%s body=%s",
                    llm_backend,
                    e.response.status_code,
                    model,
                    err_body,
                )
                raise
        else:
            if not tools_omitted_r:
                c0, m2, tc2, hn2 = _extract_tool_calls_from_completion_response(
                    data_r,
                    allowed_tool_names=allowed_names,
                )
                if tc2:
                    logger.info(
                        "agent: tool_choice=required retry produced tool_calls (llm_model_id=%s)",
                        model,
                    )
                    apply_repetition_guard_to_completion(data_r)
                    data, tools_omitted = data_r, tools_omitted_r
                    choice0, msg, tool_calls, had_native_tool_calls = (
                        c0,
                        m2,
                        tc2,
                        hn2,
                    )
            else:
                logger.warning(
                    "agent: tool_choice=required retry omitted tools (llm_model_id=%s); keeping first completion",
                    model,
                )

    if not tools_for_round and tool_calls:
        n_disc = len(tool_calls) if isinstance(tool_calls, list) else 0
        logger.warning(
            "chat tool loop round %d/%d: discarding %d tool_call(s) (no tools[] this round)",
            round_i + 1,
            max_tool_rounds_eff,
            n_disc,
        )
        messages.append(
            {
                "role": "system",
                "content": (
                    "This round did not include tool definitions in the API request. Any `tool_calls` "
                    "you produced are **discarded**. Reply with **plain text only**: merge findings from "
                    "earlier tool messages, note errors briefly, and state next steps."
                ),
            }
        )
        msg = dict(msg)
        msg.pop("tool_calls", None)
        choice0["message"] = msg
        ch_list = data.get("choices")
        if isinstance(ch_list, list) and ch_list and isinstance(ch_list[0], dict):
            ch_list[0]["message"] = msg
        tool_calls = None
        had_native_tool_calls = False

    _log_llm_completion_round(
        agent_run_id=agent_run_id,
        agent_id=agent_id if isinstance(agent_id, str) else None,
        round_i=round_i,
        model=model,
        messages=messages,
        tools_for_round=tools_for_round,
        msg=msg,
        choice0=choice0 if isinstance(choice0, dict) else {},
        tool_calls=tool_calls if isinstance(tool_calls, list) else None,
        had_native_tool_calls=had_native_tool_calls,
        log_enabled=config.AGENT_LOG_LLM_ROUNDS,
        large_context_chars=config.AGENT_LOG_LARGE_CONTEXT_CHARS,
        log_tool_names_each_round=config.AGENT_LOG_TOOL_NAMES_EACH_ROUND,
        assistant_preview_chars=config.AGENT_LOG_ASSISTANT_PREVIEW_CHARS,
    )

    if event_emit:
        tc_names = [
            (tc.get("function") or {}).get("name")
            for tc in (tool_calls or [])
            if isinstance(tc, dict)
        ]
        usage_raw = data.get("usage") if isinstance(data, dict) else None
        usage_out = usage_raw if isinstance(usage_raw, dict) else None
        _prompt_tok = usage_prompt_tokens(usage_out) if usage_out else None
        if _prompt_tok is not None:
            await enforce_agent_context_budget(
                f"round_{round_i + 1}_post_llm",
                _prompt_tok,
                round_num=round_i + 1,
            )
        await event_emit(
            {
                "type": "agent.llm_round",
                "agent_run_id": agent_run_id,
                "round": round_i + 1,
                "tool_calls": [str(x) for x in tc_names if x],
                "had_native_tool_calls": had_native_tool_calls,
                "content_excerpt": (
                    (msg.get("content") or "")[:400]
                    if isinstance(msg.get("content"), str)
                    else ""
                ),
                **({"usage": usage_out} if usage_out is not None else {}),
            }
        )

    if not tool_calls:
        need_verify = bool(
            workspace
            and isinstance(workspace, dict)
            and (
                bool(workspace.get("verify_required")) or agent_require_workspace_verify
            )
        )
        if need_verify:
            vcmd = workspace.get("verify_command") if isinstance(workspace, dict) else None
            has_cmd = isinstance(vcmd, str) and vcmd.strip()
            if bool(workspace.get("verify_required")) and not has_cmd:
                raise ValueError(
                    "Workspace has verify_required=true but no verify_command; "
                    "set verify_command via PATCH /v1/workspaces/{id}."
                )
            if agent_require_workspace_verify and not has_cmd:
                raise ValueError(
                    "agent_require_workspace_verify was set but this workspace has no verify_command configured."
                )
            if not tool_context.get("workspace_verify_succeeded"):
                raise ValueError(
                    "Workspace verify gate: run coding_workspace_verify successfully (exit 0) before "
                    "finishing, or disable verify_required / agent_require_workspace_verify."
                )
        if _sanitize_final_completion_assistant_content(data):
            logger.info(
                "agent: stripped fake tool markup from final chat.completion (round %s/%s)",
                round_i + 1,
                max_tool_rounds_eff,
            )
        if turn_hooks.sanitize_completion(data):
            logger.info(
                "agent turn hook: sanitized assistant display text (round %s/%s)",
                round_i + 1,
                max_tool_rounds_eff,
            )
        nudge_content = turn_hooks.maybe_nudge_text_only_turn(
            tool_context,
            allowed_names=allowed_names,
            round_i=round_i,
        )
        if nudge_content:
            messages.append(msg)
            messages.append({"role": "system", "content": nudge_content})
            return LlmToolRoundResult(
                continue_round=True,
                data=data,
                msg=msg,
                choice0=choice0,
                tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                had_native_tool_calls=had_native_tool_calls,
                tools_for_round=tools_for_round,
                allowed_names=allowed_names,
                model=model,
                attempts=attempts,
                llm_backend=llm_backend,
                force_no_tools_round=force_no_tools_round,
                force_no_tools_reason=force_no_tools_reason,
            )
        if event_emit:
            await event_emit(
                {
                    "type": "agent.done",
                    "agent_run_id": agent_run_id,
                    "kind": "final_text",
                    "round": round_i + 1,
                }
            )
        return LlmToolRoundResult(
            final_response=_completion_attach_agent_run_id(
                data,
                agent_run_id,
                context_meta=context_prep_meta or None,
                run_persisted=run_persisted,
                run_persist_warnings=run_persist_warnings or None,
            ),
            data=data,
            msg=msg,
            choice0=choice0,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            had_native_tool_calls=had_native_tool_calls,
            tools_for_round=tools_for_round,
            allowed_names=allowed_names,
            model=model,
            attempts=attempts,
            llm_backend=llm_backend,
            force_no_tools_round=force_no_tools_round,
            force_no_tools_reason=force_no_tools_reason,
        )

    return LlmToolRoundResult(
        data=data,
        msg=msg,
        choice0=choice0,
        tool_calls=tool_calls if isinstance(tool_calls, list) else None,
        had_native_tool_calls=had_native_tool_calls,
        tools_for_round=tools_for_round,
        allowed_names=allowed_names,
        model=model,
        attempts=attempts,
        llm_backend=llm_backend,
        force_no_tools_round=force_no_tools_round,
        force_no_tools_reason=force_no_tools_reason,
    )


__all__ = ["LlmToolRoundResult", "process_llm_tool_round"]
