"""Chat completion with tool-call loop."""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from json import JSONDecoder
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal

import httpx

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    agent_config_effective,
    agent_runs_store,
    apply_repetition_guard_to_completion,
    bind_llm_wait_notifier,
    build_media_library_context_snippet,
    build_knowledge_orchestration_snippet,
    format_ingested_audio_system_block,
    completion_quotas_from_budget,
    categories_for_matches,
    db,
    ensure_workspace,
    external_llm_should_failover,
    find_block_in_layout,
    gather_mcp_chat_tool_specs_async,
    hints_for_matches,
    http_post_chat_completions,
    ingest_chat_audio_attachments,
    ingress_openai_messages_inplace,
    llm_chat_transport,
    load_combined_skills_prompt,
    match_task_intents,
    maybe_schedule_index_on_attach,
    memory_api,
    normalize_model_catalog_owned_by,
    onboarding_for_dashboard,
    policies_map,
    prepare_chat_history_for_llm,
    reset_llm_wait_notifier,
    resolve_context_budget,
    smart_llm_routing_enabled,
    stream_chat_completions_aggregate,
    task_intent_strict_tools,
    tools_for_matches,
    unpack_llm_attempt,
    usage_prompt_tokens,
)
from apps.backend.application.agent_runtime.use_cases.chat_context_budget import ChatContextBudgetEnforcer
from apps.backend.application.agent_runtime.use_cases.chat_control import ChatControlQueue
from apps.backend.application.agent_runtime.use_cases.chat_llm_transport import execute_llm_completion_round
from apps.backend.application.agent_runtime.use_cases.chat_run_bootstrap import bootstrap_chat_run
from apps.backend.application.agent_runtime.use_cases.chat_tool_events import emit_tool_done_events, emit_tool_start_event
from apps.backend.application.agent_runtime.use_cases.chat_tool_execution import execute_tool_with_agent_policy
from apps.backend.application.agent_runtime.use_cases.chat_tool_loop import run_chat_tool_loop
from apps.backend.application.agent_runtime.use_cases.chat_tool_selection import select_tools_for_chat_turn
from apps.backend.application.agent_runtime.use_cases.chat_turn_preparation import prepare_chat_turn
from apps.backend.application.agent_runtime.use_cases.upload_storage_images import (
    dashboard_id_from_tool_result as _dashboard_id_from_tool_result,
    storage_images_from_body as _agent_storage_images_from_body,
    storage_upload_prompt as _storage_upload_prompt,
    upload_pending_storage_images as _upload_pending_storage_images_sync,
)
from apps.backend.domain.shared.identity import get_identity
from apps.backend.domain.agent_runtime.registry import get_agent_registry
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.plugin_system.capability_index import filter_merged_tools_by_capabilities
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories_for_agent,
    filter_merged_tools_by_domain,
    last_user_text,
)
from apps.backend.domain.scheduling.run_context import record_schedule_abort, record_schedule_tool_event
from apps.backend.domain.tools.executor import execute_tool
from apps.backend.domain.tools.invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
    reset_agent_run_id,
    reset_agent_task_id,
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)
from apps.backend.domain.model_routing.resolution import (
    ModelRoutingSettings,
    profile_default_model_id,
    resolve_effective_model,
)
from apps.backend.domain.model_routing.smart_route import decide_smart_backend
from apps.backend.domain.agent_runtime.persona import _append_system_block, apply_user_persona_system

logger = logging.getLogger(__name__)


def _model_routing_settings() -> ModelRoutingSettings:
    return ModelRoutingSettings(
        profile_default=config.AGENT_MODEL_PROFILE_DEFAULT,
        profile_vlm=config.AGENT_MODEL_PROFILE_VLM,
        profile_agent=config.AGENT_MODEL_PROFILE_AGENT,
        profile_coding=config.AGENT_MODEL_PROFILE_CODING,
        allow_model_override=config.AGENT_ALLOW_MODEL_OVERRIDE,
        override_roles=config.AGENT_MODEL_OVERRIDE_ROLES,
        override_anonymous=config.AGENT_MODEL_OVERRIDE_ANONYMOUS,
    )

from apps.backend.application.agent_runtime.runtime.io import *  # noqa: F403, E402
from apps.backend.application.agent_runtime.runtime.prompts import *  # noqa: F403, E402
from apps.backend.application.agent_runtime.runtime.tool_loop import *  # noqa: F403, E402

# ``import *`` skips ``_``-prefixed names unless listed in ``__all__`` (see PEP 8).


async def chat_completion(
    body: dict[str, Any],
    *,
    router_categories_header: str | None = None,
    tool_domain_header: str | None = None,
    model_profile_header: str | None = None,
    model_override_header: str | None = None,
    user_timezone_header: str | None = None,
    bearer_user_role: str | None = None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    control_queue: asyncio.Queue | None = None,
    cancel_event: asyncio.Event | None = None,
    stream_requested: bool = False,
    embedded_subagent: bool = False,
) -> dict[str, Any] | AsyncIterator[bytes]:
    # Without ``stream_requested`` + plain completion, the tool loop uses blocking HTTP; HTTP callers may
    # wrap the final JSON as SSE. True streaming is returned as an async byte iterator (upstream SSE passthrough).
    body.pop("agent_tool_mode", None)
    body.pop("agent_mode", None)
    plain_completion = _coerce_body_bool(body.pop("agent_plain_completion", None), False)
    stream_llm_ws = _coerce_body_bool(body.pop("agent_stream_llm", None), False)
    extra_cats_body = _parse_router_categories_value(body.pop("agent_router_categories", None))
    extra_cats_hdr = _parse_router_category_tokens(router_categories_header)
    cap_hints = _parse_capability_hints(body.pop("agent_capability_hints", None))
    raw_tool_dom = body.pop("TOOL_DOMAIN", None)
    body_tool_dom = (
        str(raw_tool_dom).strip().lower()
        if isinstance(raw_tool_dom, str) and raw_tool_dom.strip()
        else ""
    )
    hdr_tool_dom = (tool_domain_header or "").strip().lower()
    tool_domain = hdr_tool_dom or body_tool_dom or None
    logger.debug("tool_domain_header=%r, body_tool_domain=%r, final tool_domain=%r", tool_domain_header, body_tool_dom, tool_domain)

    _cap_cf_tok = bind_capability_confirmed(
        parse_user_capability_confirm(body.pop("agent_capability_confirm", None))
    )
    dashboard_ctx = body.pop("agent_dashboard_context", None)
    _agent_storage_images = _agent_storage_images_from_body(body.pop("agent_storage_images", None))
    _raw_max_rounds = body.pop("agent_max_tool_rounds", None)
    _raw_llm_be = body.pop("agent_llm_backend", None)
    _raw_catalog_owned = body.pop("agent_model_catalog_owned_by", None)
    catalog_owned_by = normalize_model_catalog_owned_by(_raw_catalog_owned)
    _raw_tool_allow = body.pop("agent_tool_name_allowlist", None)
    _raw_tools_ranking = body.pop("agent_tools_ranking_enabled", None)
    tools_ranking_enabled = bool(config.AGENT_TOOLS_RANKING_ENABLED)
    if _raw_tools_ranking is not None:
        tools_ranking_enabled = _coerce_body_bool(_raw_tools_ranking, tools_ranking_enabled)
    agent_id = body.pop("agent_id", None)
    if isinstance(agent_id, str):
        agent_id = agent_id.strip() or None
    if not embedded_subagent:
        dash_id = (
            str(dashboard_ctx.get("dashboard_id") or "").strip()
            if isinstance(dashboard_ctx, dict)
            else ""
        )
        if not agent_id and dash_id:
            agent_id = "dashboard"
        elif not agent_id:
            agent_id = "general"
        _chat_surface_agents = frozenset({"general", "dashboard", "creative"})
        if agent_id == "dashboard" and not dash_id and not _agent_storage_images:
            logger.info("chat_completion: dashboard agent requires agent_dashboard_context — using general")
            agent_id = "general"
        elif agent_id not in _chat_surface_agents:
            logger.info(
                "chat_completion: forcing agent_id %r -> general (use delegate for specialists)",
                agent_id,
            )
            agent_id = "general"
    parent_agent_run_id = body.pop("agent_parent_run_id", None)
    if isinstance(parent_agent_run_id, str):
        parent_agent_run_id = parent_agent_run_id.strip() or None
    else:
        parent_agent_run_id = None
    _pre_run_id = body.pop("agent_run_id", None)
    _active_task_body = body.pop("agent_active_task_id", None)
    permission_ask = _coerce_body_bool(body.pop("agent_permission_ask", None), False)
    agent_unattended = _coerce_body_bool(body.pop("agent_unattended", None), False)
    _raw_tools_full_schema = body.pop("agent_tools_full_schema", None)
    tools_full_schema = _coerce_body_bool(
        _raw_tools_full_schema,
        config.AGENT_TOOLS_FULL_SCHEMA,
    )
    if agent_unattended:
        permission_ask = False
    agent_require_workspace_verify = _coerce_body_bool(
        body.pop("agent_require_workspace_verify", None), False
    )
    _raw_plan_delegate_mode = body.pop("agent_plan_delegate_mode", None)
    _raw_delegate_mode = body.pop("agent_delegate_mode", None)
    agent_delegate_mode: str | None = None
    for raw in (_raw_delegate_mode, _raw_plan_delegate_mode):
        if isinstance(raw, str) and raw.strip():
            agent_delegate_mode = raw.strip()
            break
    _raw_delegate_paths = body.pop("agent_delegate_allowed_paths", None)
    delegate_allowed_paths: list[str] | None = None
    if isinstance(_raw_delegate_paths, list):
        delegate_allowed_paths = [str(p).strip() for p in _raw_delegate_paths if str(p).strip()]
    _raw_delegate_branch = body.pop("agent_delegate_required_branch", None)
    delegate_required_branch: str | None = None
    if isinstance(_raw_delegate_branch, str):
        delegate_required_branch = _raw_delegate_branch.strip() or None
    _handoff_collector = body.pop("agent_handoff_artifact_collector", None)
    # Benchmark execution stays an admin/harness concern. Chat only binds the
    # run context so model/provider harness overrides apply during this runtime.
    _raw_benchmark_run_id = body.pop("benchmark_run_id", None)
    _parsed_benchmark_run_id: uuid.UUID | None = None
    _bench_run_ctx_tok = None
    _harness_prof_tok = None
    _parent_cancel_bridge_task: asyncio.Task[None] | None = None
    if _raw_benchmark_run_id is not None:
        try:
            _parsed_benchmark_run_id = uuid.UUID(str(_raw_benchmark_run_id).strip())
        except (ValueError, TypeError):
            _parsed_benchmark_run_id = None
    if _parsed_benchmark_run_id is not None:
        from apps.backend.domain.shared.identity import set_benchmark_run_id

        _bench_run_ctx_tok = set_benchmark_run_id(_parsed_benchmark_run_id)
    try:
        run_bootstrap = await bootstrap_chat_run(
            body=body,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            embedded_subagent=embedded_subagent,
            bearer_user_role=bearer_user_role,
            agent_storage_images=_agent_storage_images,
            pre_run_id=_pre_run_id,
            parent_agent_run_id=parent_agent_run_id,
            cancel_event=cancel_event,
            event_emit=event_emit,
            agent_unattended=agent_unattended,
            agent_delegate_mode=agent_delegate_mode,
            delegate_allowed_paths=delegate_allowed_paths,
            delegate_required_branch=delegate_required_branch,
            handoff_collector=_handoff_collector,
            active_task_body=_active_task_body,
            agent_require_workspace_verify=agent_require_workspace_verify,
        )
    except Exception:
        if _bench_run_ctx_tok is not None:
            from apps.backend.domain.shared.identity import reset_benchmark_run_id

            reset_benchmark_run_id(_bench_run_ctx_tok)
            _bench_run_ctx_tok = None
        raise
    workspace_id = run_bootstrap.workspace_id
    workspace = run_bootstrap.workspace
    workspace_token = run_bootstrap.workspace_token
    tenant_id = run_bootstrap.tenant_id
    user_id = run_bootstrap.user_id
    _cfg_tid = run_bootstrap.cfg_tid
    _router_strict_default = run_bootstrap.router_strict_default
    _catalog_after_first_round = run_bootstrap.catalog_after_first_round
    _tool_choice_required_retry = run_bootstrap.tool_choice_required_retry
    user_obj = run_bootstrap.user_obj
    _is_admin = run_bootstrap.is_admin
    tool_context = run_bootstrap.tool_context
    agent_run_id = run_bootstrap.agent_run_id
    _parent_cancel_bridge_task = run_bootstrap.parent_cancel_bridge_task
    _llm_wait_token = run_bootstrap.llm_wait_token
    conversation_uuid = run_bootstrap.conversation_uuid
    active_task_id = run_bootstrap.active_task_id
    _run_persisted = run_bootstrap.run_persisted
    _run_persist_warnings = run_bootstrap.run_persist_warnings
    _run_ctx_tok = run_bootstrap.run_ctx_token
    _task_ctx_tok = run_bootstrap.task_ctx_token
    _run_finish_status = run_bootstrap.run_finish_status
    _run_finish_error = run_bootstrap.run_finish_error
    workspace_auto_created = run_bootstrap.workspace_auto_created
    workspace_bound_from_conversation = run_bootstrap.workspace_bound_from_conversation
    agent_auto_routed = run_bootstrap.agent_auto_routed

    try:

        turn_prep = await prepare_chat_turn(
            body=body,
            tool_context=tool_context,
            conversation_uuid=conversation_uuid,
            user_id=user_id,
            tenant_id=int(tenant_id) if tenant_id is not None else None,
            cfg_tid=_cfg_tid,
            catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
            plain_completion=plain_completion,
            model_profile_header=model_profile_header,
            model_override_header=model_override_header,
            bearer_user_role=bearer_user_role,
            embedded_subagent=embedded_subagent,
            dashboard_ctx=dashboard_ctx,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            agent_storage_images=_agent_storage_images,
            is_admin=_is_admin,
            active_task_id=active_task_id,
            agent_delegate_mode=agent_delegate_mode,
            user_timezone_header=user_timezone_header,
            workspace=workspace if isinstance(workspace, dict) else None,
            raw_tools_ranking=_raw_tools_ranking,
            raw_tools_full_schema=_raw_tools_full_schema,
            raw_max_rounds=_raw_max_rounds,
            raw_llm_backend=_raw_llm_be,
            tools_ranking_enabled=tools_ranking_enabled,
            tools_full_schema=tools_full_schema,
        )
        messages = turn_prep.messages
        model = turn_prep.model
        model_reason = turn_prep.model_reason
        profile_key = turn_prep.profile_key
        model_is_override = turn_prep.model_is_override
        catalog_owned_by = turn_prep.catalog_owned_by
        tools_ranking_enabled = turn_prep.tools_ranking_enabled
        tools_full_schema = turn_prep.tools_full_schema
        _router_strict_default = turn_prep.router_strict_default
        _task_intent_user_text = turn_prep.task_intent_user_text
        _task_intent_matches = turn_prep.task_intent_matches
        _catalog_after_first_round = turn_prep.catalog_after_first_round
        _tool_choice_required_retry = turn_prep.tool_choice_required_retry
        max_tool_rounds_eff = turn_prep.max_tool_rounds_eff
        _thrash_enabled = turn_prep.thrash_enabled
        _thrash_streak_max = turn_prep.thrash_streak_max
        _doom_enabled = turn_prep.doom_enabled
        _doom_streak_max = turn_prep.doom_streak_max
        _context_prep_meta = turn_prep.context_prep_meta
        _compaction_attempt = turn_prep.compaction_attempt
        _context_budget = turn_prep.context_budget
        smart_route_reason = turn_prep.smart_route_reason
        attempts = turn_prep.attempts
        llm_backend = turn_prep.llm_backend
        _harness_prof_tok = turn_prep.harness_profile_token

        _ctx_win = (
            int(_context_budget.context_window_tokens or 0)
            if _context_budget is not None
            else 0
        )
        tool_selection = await select_tools_for_chat_turn(
            body=body,
            plain_completion=plain_completion,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            tool_domain=tool_domain,
            task_intent_user_text=_task_intent_user_text,
            task_intent_matches=_task_intent_matches,
            extra_cats_body=extra_cats_body,
            extra_cats_hdr=extra_cats_hdr,
            cap_hints=cap_hints,
            cfg_tid=_cfg_tid,
            raw_tool_allow=_raw_tool_allow,
            dashboard_ctx=dashboard_ctx,
            model=model if isinstance(model, str) else None,
            context_window_tokens=_ctx_win,
            tools_ranking_enabled=tools_ranking_enabled,
            tools_full_schema=tools_full_schema,
            agent_run_id=agent_run_id,
            tool_context=tool_context,
            router_strict_default=_router_strict_default,
        )
        cats = tool_selection.cats
        routed_category = tool_selection.routed_category
        tools_for_request = tool_selection.tools_for_request
        forward_names = tool_selection.forward_names
        turn_hooks = tool_selection.turn_hooks
        _tf_plan = tool_selection.forward_plan
        pause_between_rounds = _coerce_body_bool(body.get("agent_pause_between_rounds"), False)
        if pause_between_rounds and control_queue is None:
            pause_between_rounds = False

        options = {
            k: v
            for k, v in body.items()
            if k not in ("messages", "model", "tools", "stream", *_BODY_KEYS_STRIP_FROM_LLM)
        }

        if (
            stream_requested
            and plain_completion
            and not pause_between_rounds
            and control_queue is None
        ):
            payload_stream_base: dict[str, Any] = {"messages": messages, **options}

            async def _sse_stream() -> AsyncIterator[bytes]:
                async for chunk in _async_iter_chat_completion_sse(
                    attempts,
                    payload_stream_base,
                    llm_backend=llm_backend,
                    profile_key=profile_key,
                    timeout=config.LLM_CHAT_TIMEOUT_SEC,
                    model_routing_settings=_model_routing_settings(),
                ):
                    yield chunk

            return _sse_stream()

        control = ChatControlQueue(
            messages=messages,
            tools_for_request=tools_for_request,
            tools_full_schema=tools_full_schema,
            control_queue=control_queue,
            cancel_event=cancel_event,
            event_emit=event_emit,
            agent_run_id=agent_run_id,
            max_tool_rounds_eff=max_tool_rounds_eff,
        )
        handle_control_dict = control.handle_control_dict
        drain_control_queue = control.drain
        wait_for_continue_step_after_round = control.wait_for_continue_step_after_round

        forwarded_preview = [n for t in tools_for_request if (n := _tool_spec_name(t)) is not None]
        if event_emit:
            await event_emit(
                {
                    "type": "agent.context_update",
                    "agent_run_id": agent_run_id,
                    "context": dict(tool_context.get("chat_context_meta") or {}),
                }
            )
        if event_emit:
            await event_emit(
                {
                    "type": "agent.session",
                    "agent_run_id": agent_run_id,
                    "routed_category": routed_category,
                    "router_categories": sorted(cats),
                    "forwarded_tools": forwarded_preview,
                    "effective_model": model,
                    "model_resolution": model_reason,
                    "llm_backend": llm_backend,
                    "smart_route_reason": smart_route_reason or None,
                    "effective_agent_id": agent_id,
                    "workspace_id": str(workspace["id"])
                    if workspace and workspace.get("id")
                    else None,
                    "workspace_auto_created": workspace_auto_created,
                    "workspace_bound": workspace_bound_from_conversation,
                    "agent_auto_routed": agent_auto_routed,
                    "context": tool_context.get("chat_context_meta") or None,
                }
            )

        return await run_chat_tool_loop(
            messages=messages,
            tool_context=tool_context,
            context_prep_meta=_context_prep_meta,
            model=model if isinstance(model, str) else None,
            event_emit=event_emit,
            agent_run_id=agent_run_id,
            plain_completion=plain_completion,
            tools_for_request=tools_for_request,
            max_tool_rounds_eff=max_tool_rounds_eff,
            catalog_after_first_round=_catalog_after_first_round,
            tool_forward_plan=_tf_plan,
            config_tool_choice_required_retry=_tool_choice_required_retry,
            stream_llm_ws=stream_llm_ws,
            options=options,
            attempts=attempts,
            llm_backend=llm_backend,
            profile_key=profile_key,
            catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
            cancel_event=cancel_event,
            control_queue=control_queue,
            turn_hooks=turn_hooks,
            permission_ask=permission_ask,
            handle_control_dict=handle_control_dict,
            drain_control_queue=drain_control_queue,
            wait_for_continue_step_after_round=wait_for_continue_step_after_round,
            pause_between_rounds=pause_between_rounds,
            tools_full_schema=tools_full_schema,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            workspace=workspace if isinstance(workspace, dict) else None,
            workspace_auto_created=workspace_auto_created,
            workspace_bound_from_conversation=workspace_bound_from_conversation,
            agent_auto_routed=agent_auto_routed,
            agent_require_workspace_verify=agent_require_workspace_verify,
            model_reason=model_reason,
            routed_category=routed_category,
            cats=cats,
            user_id=user_id,
            tenant_id=int(tenant_id) if tenant_id is not None else None,
            agent_storage_images=_agent_storage_images,
            is_admin=_is_admin,
            thrash_enabled=_thrash_enabled,
            thrash_streak_max=_thrash_streak_max,
            doom_enabled=_doom_enabled,
            doom_streak_max=_doom_streak_max,
            run_persisted=_run_persisted,
            run_persist_warnings=_run_persist_warnings,
        )

        logger.warning(
            "max tool rounds (%s) exceeded ctx_msgs=%d ctx_text_chars~=%d",
            max_tool_rounds_eff,
            len(messages),
            _approx_text_chars_in_messages(messages),
        )
        if event_emit:
            await event_emit(
                {
                    "type": "agent.done",
                    "agent_run_id": agent_run_id,
                    "kind": "max_tool_rounds",
                    "round": max_tool_rounds_eff,
                }
            )
        return _completion_attach_agent_run_id(
            data,
            agent_run_id,
            context_meta=_context_prep_meta or None,
            run_persisted=_run_persisted,
            run_persist_warnings=_run_persist_warnings or None,
        )
    except AgentChatCancelled:
        _run_finish_status = "cancelled"
        _run_finish_error = "cancelled"
        raise

    finally:
        if _parent_cancel_bridge_task is not None:
            _parent_cancel_bridge_task.cancel()
            try:
                await _parent_cancel_bridge_task
            except asyncio.CancelledError:
                pass
        if not embedded_subagent:
            from apps.backend.domain.agent_runtime.run_cancel import unregister_parent_cancel

            unregister_parent_cancel(agent_run_id)
        if _llm_wait_token is not None:
            reset_llm_wait_notifier(_llm_wait_token)
        reset_agent_run_id(_run_ctx_tok)
        reset_agent_task_id(_task_ctx_tok)
        if user_id is not None and tenant_id is not None and _run_persisted:
            try:
                agent_runs_store.finish_run(
                    run_id=uuid.UUID(agent_run_id),
                    status=_run_finish_status,
                    error=_run_finish_error,
                )
            except Exception:
                logger.warning("agent_runs finish failed run_id=%s", agent_run_id, exc_info=True)
        reset_capability_confirmed(_cap_cf_tok)
        from apps.backend.domain.shared.identity import reset_benchmark_run_id, reset_harness_profile, reset_workspace

        if _bench_run_ctx_tok is not None:
            reset_benchmark_run_id(_bench_run_ctx_tok)
        if _harness_prof_tok is not None:
            reset_harness_profile(_harness_prof_tok)
        if workspace_token:
            reset_workspace(workspace_token)


from apps.backend.application.agent_runtime.runtime import embedded_subagent as _embedded_subagent  # noqa: E402

_embedded_subagent.register_embedded_chat_completion(chat_completion)
