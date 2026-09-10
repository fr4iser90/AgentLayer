"""Prepare messages, model routing, and context budgets for agent chat."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    ContextPrepMeta,
    agent_config_effective,
    apply_budget_to_meta,
    categories_for_matches,
    format_ingested_audio_system_block,
    hints_for_matches,
    ingress_openai_messages_inplace,
    ingest_chat_audio_attachments,
    llm_chat_transport,
    match_task_intents,
    prepare_chat_history_for_llm,
    smart_llm_routing_enabled,
    tools_for_matches,
)
from apps.backend.application.agent_runtime.runtime.io import _apply_tool_prefetch
from apps.backend.domain.agent_runtime.persona import _append_system_block, apply_user_persona_system
from apps.backend.application.agent_runtime.runtime.prompts import (
    _inject_agent_system_prompt,
    _inject_dashboard_context,
    _inject_system_prompt,
    _inject_user_memory_context,
    _inject_user_secrets_bootstrap,
    _inject_workspace_bound_context,
    _inject_workspace_retrieval_bootstrap,
    _inject_workspace_verify_hints,
    _inject_workspace_agent_instructions,
)
from apps.backend.application.agent_runtime.use_cases.chat_turn_agent_blocks import (
    inject_agent_catalog_blocks,
    inject_conversation_goal_block,
    inject_knowledge_orchestration_block,
)
from apps.backend.application.agent_runtime.use_cases.chat_turn_inject_state import (
    apply_omit_stub_and_ledger,
    inject_agent_key,
    load_prior_inject_digests,
    needs_full_reinject,
    persist_inject_digests,
)
from apps.backend.domain.model_routing.smart_route import decide_smart_backend
from apps.backend.domain.model_routing.resolution import ModelRoutingSettings, resolve_effective_model
from apps.backend.infrastructure.agent_runtime.context_budget import (
    completion_quotas_from_budget,
    resolve_context_budget,
)
from apps.backend.domain.plugin_system.tool_routing import last_user_text

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


@dataclass
class ChatTurnPreparation:
    messages: list[dict[str, Any]]
    model: str
    model_reason: str
    profile_key: str
    model_is_override: bool
    catalog_owned_by: str | None
    tools_ranking_enabled: bool
    tools_full_schema: bool
    router_strict_default: bool
    task_intent_user_text: str
    task_intent_matches: list[Any]
    catalog_after_first_round: bool
    tool_choice_required_retry: bool
    max_tool_rounds_eff: int
    thrash_enabled: bool
    thrash_streak_max: int
    doom_enabled: bool
    doom_streak_max: int
    output_echo_enabled: bool
    output_echo_streak_max: int
    output_echo_min_chars: int
    result_echo_enabled: bool
    result_echo_streak_max: int
    result_echo_min_chars: int
    context_prep_meta: dict[str, Any]
    compaction_attempt: tuple[str, dict[str, str], str, str] | None
    context_budget: Any
    smart_route_reason: str
    attempts: list[tuple[str, dict[str, str], str, str]]
    llm_backend: str
    harness_profile_token: Any
    context_injections: list[dict[str, Any]]


async def prepare_chat_turn(
    *,
    body: dict[str, Any],
    tool_context: dict[str, Any],
    conversation_uuid: uuid.UUID | None,
    user_id: Any,
    tenant_id: int | None,
    cfg_tid: int | None,
    catalog_owned_by: str | None,
    plain_completion: bool,
    model_profile_header: str | None,
    model_override_header: str | None,
    bearer_user_role: str | None,
    embedded_subagent: bool,
    dashboard_ctx: Any,
    agent_id: str | None,
    agent_storage_images: list[dict[str, Any]],
    is_admin: bool,
    active_task_id: str | None,
    agent_delegate_mode: str | None,
    user_timezone_header: str | None,
    workspace: dict[str, Any] | None,
    raw_tools_ranking: Any,
    raw_tools_full_schema: Any,
    raw_max_rounds: Any,
    raw_llm_backend: Any,
    tools_ranking_enabled: bool,
    tools_full_schema: bool,
) -> ChatTurnPreparation:
    from apps.backend.domain.agent_runtime.context_injection import (
        begin_inject_ledger,
        clear_omitable_digests,
        take_inject_digests,
    )

    ace = agent_config_effective
    routing_settings = _model_routing_settings()
    _aid_key = inject_agent_key(agent_id)
    _prior_digests = load_prior_inject_digests(user_id, conversation_uuid, _aid_key)

    chat_history_raw = list(body.get("messages") or [])
    context_prep_meta: dict[str, Any] = {}
    compaction_attempt: tuple[str, dict[str, str], str, str] | None = None
    prep_context_budget = None
    if config.CHAT_CONTEXT_PREP_ENABLED and chat_history_raw:
        _prep_model, _, _prep_profile, _prep_override = resolve_effective_model(
            messages=chat_history_raw,
            body_model=body.get("model"),
            profile_header=model_profile_header,
            override_header=model_override_header,
            bearer_user_role=bearer_user_role,
            embedded_subagent=embedded_subagent,
            settings=routing_settings,
        )
        _prep_catalog = catalog_owned_by
        if not plain_completion:
            from apps.backend.domain.model_routing.catalog_chat import finalize_catalog_chat_llm

            _prep_model, _prep_catalog = finalize_catalog_chat_llm(
                model=_prep_model,
                profile_key=_prep_profile,
                is_override=_prep_override,
                catalog_owned_by=_prep_catalog,
            )
        if _prep_catalog:
            try:
                _prep_attempts, _ = llm_chat_transport(
                    _prep_model,
                    _prep_profile,
                    _prep_override,
                    catalog_owned_by=_prep_catalog,
                )
                if _prep_attempts:
                    compaction_attempt = _prep_attempts[0]
            except ValueError as e:
                logger.warning("chat context compaction: LLM transport unavailable: %s", e)

        prep_context_budget = resolve_context_budget(
            str(_prep_model or ""),
            catalog_owned_by=_prep_catalog,
        )

        chat_history_raw, _ctx_meta = await prepare_chat_history_for_llm(
            chat_history_raw,
            conversation_id=conversation_uuid,
            user_id=user_id if isinstance(user_id, uuid.UUID) else None,
            compaction_model=_prep_model,
            compaction_attempt=compaction_attempt,
            context_budget=prep_context_budget,
        )
        body["messages"] = chat_history_raw
        context_prep_meta = _ctx_meta.as_dict()
    tool_context["chat_context_meta"] = context_prep_meta

    # Force full re-inject of omitable kinds after compaction or periodic refresh.
    if needs_full_reinject(context_prep_meta, body.get("messages") or []) and _prior_digests:
        _prior_digests = clear_omitable_digests(_prior_digests)

    _omit_enabled = (
        bool(getattr(config, "CHAT_CONTEXT_INJECT_OMIT", True))
        and not embedded_subagent
        and conversation_uuid is not None
    )
    _inject_tok = begin_inject_ledger(
        prior_digests=_prior_digests,
        skip_llm_when_unchanged=_omit_enabled,
    )

    messages = _inject_system_prompt(
        list(body.get("messages") or []),
        system_prompt_extra=config.SYSTEM_PROMPT_EXTRA,
    )
    ingress_openai_messages_inplace(messages, tenant_id=int(tenant_id), user_id=user_id)
    _ingested_audio: list[dict[str, Any]] = []
    if user_id is not None and tenant_id is not None and isinstance(user_id, uuid.UUID):
        _ingested_audio = ingest_chat_audio_attachments(
            messages, tenant_id=int(tenant_id), user_id=user_id
        )
        _audio_block = format_ingested_audio_system_block(_ingested_audio)
        if _audio_block:
            messages = _append_system_block(
                messages, _audio_block, kind="audio_ingest", label="Ingested audio"
            )
    messages = _inject_dashboard_context(messages, dashboard_ctx)
    if agent_id:
        messages = _inject_agent_system_prompt(messages, agent_id)
    if conversation_uuid is not None and user_id is not None and isinstance(user_id, uuid.UUID):
        try:
            messages = inject_conversation_goal_block(
                messages,
                agent_id=agent_id if isinstance(agent_id, str) else None,
                user_id=user_id,
                conversation_id=conversation_uuid,
            )
        except Exception:
            logger.exception("conversation goal prompt inject failed")
    messages = inject_agent_catalog_blocks(
        messages,
        agent_id=agent_id,
        user_id=user_id,
        tenant_id=tenant_id,
        is_admin=is_admin,
        active_task_id=active_task_id,
        plain_completion=plain_completion,
        agent_delegate_mode=agent_delegate_mode,
        agent_storage_images=agent_storage_images,
        ingested_audio=_ingested_audio,
    )
    pf = body.get("tool_prefetch")
    if isinstance(pf, dict):
        _apply_tool_prefetch(messages, pf, create_tool_max_bytes=config.CREATE_TOOL_MAX_BYTES)
    messages = apply_user_persona_system(messages)
    from apps.backend.domain.agent_runtime.time_context import apply_current_time_context

    messages = apply_current_time_context(
        messages,
        user_id,
        tenant_id,
        request_timezone=user_timezone_header,
    )
    messages = _inject_user_memory_context(messages, dashboard_ctx)
    messages = _inject_user_secrets_bootstrap(messages, user_id)
    messages = _inject_workspace_bound_context(
        messages, workspace, agent_id if isinstance(agent_id, str) else None
    )
    messages = _inject_workspace_retrieval_bootstrap(
        messages, workspace, agent_id if isinstance(agent_id, str) else None
    )
    messages = _inject_workspace_agent_instructions(
        messages, workspace, agent_id if isinstance(agent_id, str) else None
    )
    messages = _inject_workspace_verify_hints(messages, workspace)
    messages = inject_knowledge_orchestration_block(
        messages, agent_id=agent_id, cfg_tid=cfg_tid
    )

    model, model_reason, profile_key, model_is_override = resolve_effective_model(
        messages=messages,
        body_model=body.get("model"),
        profile_header=model_profile_header,
        override_header=model_override_header,
        bearer_user_role=bearer_user_role,
        embedded_subagent=embedded_subagent,
        settings=routing_settings,
    )
    if not plain_completion:
        from apps.backend.domain.model_routing.catalog_chat import finalize_catalog_chat_llm

        model, catalog_owned_by = finalize_catalog_chat_llm(
            model=model,
            profile_key=profile_key,
            is_override=model_is_override,
            catalog_owned_by=catalog_owned_by,
        )
    from apps.backend.domain.shared.identity import set_harness_profile

    _harness_prof_tok = set_harness_profile(
        str(catalog_owned_by or "").strip() or None,
        str(model or "").strip() or None,
    )
    if raw_tools_ranking is None and cfg_tid is not None:
        tools_ranking_enabled = ace.effective_bool(
            "tool_forward.ranking_enabled",
            tenant_id=cfg_tid,
            default=tools_ranking_enabled,
        )
    if raw_tools_full_schema is None and cfg_tid is not None:
        tools_full_schema = ace.effective_bool(
            "tool_forward.full_schema",
            tenant_id=cfg_tid,
            default=tools_full_schema,
        )
    _router_strict_default = ace.effective_bool(
        "tool_routing.router_strict_default",
        tenant_id=cfg_tid,
        default=config.AGENT_ROUTER_STRICT_DEFAULT,
    )
    _task_intent_user_text = last_user_text(messages)
    _task_intent_matches = (
        match_task_intents(_task_intent_user_text, tenant_id=cfg_tid)
        if not plain_completion
        else []
    )
    _task_intent_tools = tools_for_matches(_task_intent_matches)
    if _task_intent_matches:
        _task_intent_ids = [m.intent_id for m in _task_intent_matches]
        tool_context["task_intent_overlay"] = {
            "intent_ids": _task_intent_ids,
            "categories": sorted(categories_for_matches(_task_intent_matches)),
            "tools": sorted(_task_intent_tools),
        }
        _task_intent_hints = hints_for_matches(_task_intent_matches)
        if _task_intent_hints:
            messages = _append_system_block(
                messages,
                "Task intent overlay matched: "
                + ", ".join(_task_intent_ids)
                + "\n"
                + "\n".join(f"- {hint}" for hint in _task_intent_hints),
                kind="task_intent",
                label="Task intent overlay",
            )
    _catalog_after_first_round = ace.effective_bool(
        "tool_forward.catalog_after_first_round",
        tenant_id=cfg_tid,
        default=config.AGENT_TOOLS_CATALOG_AFTER_FIRST_ROUND,
    )
    _tool_choice_required_retry = ace.effective_bool(
        "agent.tool_choice_required_retry",
        tenant_id=cfg_tid,
        default=config.AGENT_TOOL_CHOICE_REQUIRED_RETRY,
    )
    max_tool_rounds_eff = (
        ace.subagent_max_tool_rounds(tenant_id=cfg_tid)
        if embedded_subagent
        else ace.max_tool_rounds(tenant_id=cfg_tid)
    )
    _thrash_enabled = ace.tool_thrash_enabled(tenant_id=cfg_tid)
    _thrash_streak_max = ace.tool_thrash_streak_max(tenant_id=cfg_tid)
    _doom_enabled = ace.doom_loop_enabled(tenant_id=cfg_tid)
    _doom_streak_max = ace.doom_loop_streak_max(tenant_id=cfg_tid)
    from apps.backend.infrastructure.agent_runtime import agent_config_echo as ace_echo

    _output_echo_enabled = ace_echo.assistant_output_echo_enabled(tenant_id=cfg_tid)
    _output_echo_streak_max = ace_echo.assistant_output_echo_streak_max(tenant_id=cfg_tid)
    _output_echo_min_chars = ace_echo.assistant_output_echo_min_chars(tenant_id=cfg_tid)
    _result_echo_enabled = ace_echo.tool_result_echo_enabled(tenant_id=cfg_tid)
    _result_echo_streak_max = ace_echo.tool_result_echo_streak_max(tenant_id=cfg_tid)
    _result_echo_min_chars = ace_echo.tool_result_echo_min_chars(tenant_id=cfg_tid)
    if not embedded_subagent and raw_max_rounds is not None:
        try:
            client_v = int(raw_max_rounds)
            if client_v <= 0:
                max_tool_rounds_eff = ace.max_tool_rounds(tenant_id=cfg_tid)
            else:
                base_max = ace.max_tool_rounds(tenant_id=cfg_tid)
                upper = (
                    base_max
                    if base_max < config.MAX_TOOL_ROUNDS_CAP
                    else config.MAX_TOOL_ROUNDS_CAP
                )
                max_tool_rounds_eff = max(1, min(client_v, upper))
        except (TypeError, ValueError):
            pass
    tool_context["parent_effective_model"] = model
    if catalog_owned_by:
        tool_context["parent_model_catalog_owned_by"] = catalog_owned_by
    _context_budget = resolve_context_budget(
        str(model or ""),
        catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
    )
    tool_context["_context_budget"] = _context_budget
    if compaction_attempt is not None:
        tool_context["_compaction_model"] = str(model or "")
        tool_context["compaction_attempt"] = compaction_attempt
    if _context_budget is not None:
        _meta_obj = ContextPrepMeta()
        apply_budget_to_meta(_meta_obj, _context_budget)
        for key, val in _meta_obj.as_dict().items():
            if val is not None and val != "" and val != 0:
                context_prep_meta[key] = val
        tool_context["chat_context_meta"] = context_prep_meta
        _quotas = completion_quotas_from_budget(_context_budget)
        logger.info(
            "chat context budget: model=%r window=%d soft=%d hard=%d tools=%d max_tools=%d source=%s",
            model,
            _context_budget.context_window_tokens,
            _context_budget.soft_limit_tokens,
            _context_budget.hard_limit_tokens,
            _quotas.tools_budget_tokens,
            _quotas.max_tool_count,
            _context_budget.source,
        )
    elif str(model or "").strip():
        logger.warning(
            "chat context budget: no context window for model=%r provider=%r — "
            "set CHAT_CONTEXT_MODEL_BUDGET_OVERRIDES or ensure GET /v1/models exposes n_ctx",
            model,
            catalog_owned_by,
        )
    smart_route_reason = ""
    backend_override: Literal["provider", "provider_db"] | None = None
    if isinstance(raw_llm_backend, str):
        lo = raw_llm_backend.strip().lower()
        if lo in ("provider",):
            backend_override = "provider"
        elif lo == "provider_db":
            backend_override = "provider_db"
    if backend_override is None and not plain_completion and smart_llm_routing_enabled():
        # Smart routing: 0–1 extra local router call, then one main completion — never two externals.
        bo, smart_route_reason = await asyncio.to_thread(decide_smart_backend, messages)
        backend_override = bo
        logger.info("smart LLM route: %s -> backend=%s", smart_route_reason, bo)
    elif backend_override is not None:
        logger.info("chat_completion: agent_llm_backend override -> %s", backend_override)
    attempts, llm_backend = llm_chat_transport(
        model,
        profile_key,
        model_is_override,
        backend_override=backend_override,
        catalog_owned_by=catalog_owned_by,
    )

    messages, context_injections = apply_omit_stub_and_ledger(messages, _inject_tok)
    persist_inject_digests(user_id, conversation_uuid, _aid_key, take_inject_digests())

    return ChatTurnPreparation(
        messages=messages,
        model=model,
        model_reason=model_reason,
        profile_key=profile_key,
        model_is_override=model_is_override,
        catalog_owned_by=catalog_owned_by if isinstance(catalog_owned_by, str) else None,
        tools_ranking_enabled=tools_ranking_enabled,
        tools_full_schema=tools_full_schema,
        router_strict_default=_router_strict_default,
        task_intent_user_text=_task_intent_user_text,
        task_intent_matches=_task_intent_matches,
        catalog_after_first_round=_catalog_after_first_round,
        tool_choice_required_retry=_tool_choice_required_retry,
        max_tool_rounds_eff=max_tool_rounds_eff,
        thrash_enabled=_thrash_enabled,
        thrash_streak_max=_thrash_streak_max,
        doom_enabled=_doom_enabled,
        doom_streak_max=_doom_streak_max,
        output_echo_enabled=_output_echo_enabled,
        output_echo_streak_max=_output_echo_streak_max,
        output_echo_min_chars=_output_echo_min_chars,
        result_echo_enabled=_result_echo_enabled,
        result_echo_streak_max=_result_echo_streak_max,
        result_echo_min_chars=_result_echo_min_chars,
        context_prep_meta=context_prep_meta,
        compaction_attempt=compaction_attempt,
        context_budget=_context_budget,
        smart_route_reason=smart_route_reason,
        attempts=attempts,
        llm_backend=llm_backend,
        harness_profile_token=_harness_prof_tok,
        context_injections=context_injections,
    )


__all__ = ["ChatTurnPreparation", "prepare_chat_turn"]
