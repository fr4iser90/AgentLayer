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
    build_media_library_context_snippet,
    build_knowledge_orchestration_snippet,
    categories_for_matches,
    format_ingested_audio_system_block,
    hints_for_matches,
    ingress_openai_messages_inplace,
    ingest_chat_audio_attachments,
    load_combined_skills_prompt,
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
)
from apps.backend.application.agent_runtime.use_cases.upload_storage_images import (
    storage_upload_prompt as _storage_upload_prompt,
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
    context_prep_meta: dict[str, Any]
    compaction_attempt: tuple[str, dict[str, str], str, str] | None
    context_budget: Any
    smart_route_reason: str
    attempts: list[tuple[str, dict[str, str], str, str]]
    llm_backend: str
    harness_profile_token: Any


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
    ace = agent_config_effective
    routing_settings = _model_routing_settings()

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
            messages = _append_system_block(messages, _audio_block)
    messages = _inject_dashboard_context(messages, dashboard_ctx)
    if agent_id:
        messages = _inject_agent_system_prompt(messages, agent_id)
    if agent_storage_images:
        messages = _append_system_block(messages, _storage_upload_prompt(agent_storage_images))
    if agent_id == "general":
        from apps.backend.application.agent_runtime.runtime.embedded_subagent import (
            build_delegate_agents_catalog_snippet,
        )

        messages = _append_system_block(
            messages, build_delegate_agents_catalog_snippet(caller_is_admin=is_admin)
        )
        from apps.backend.domain.agent_runtime.task_prompt import build_agent_tasks_context_snippet

        tasks_snip = build_agent_tasks_context_snippet(active_task_id=active_task_id)
        if tasks_snip:
            messages = _append_system_block(messages, tasks_snip)
    if agent_id in ("general", "dashboard") and user_id is not None and tenant_id is not None:
        _media_snip = build_media_library_context_snippet(
            user_id=user_id if isinstance(user_id, uuid.UUID) else None,
            tenant_id=int(tenant_id),
            ingested_audio=_ingested_audio,
            caller_is_admin=is_admin,
        )
        if _media_snip:
            messages = _append_system_block(messages, _media_snip)
    if agent_id and not plain_completion:
        skills_snip = load_combined_skills_prompt(
            agent_id, delegate_mode=agent_delegate_mode
        )
        if skills_snip:
            messages = _append_system_block(messages, skills_snip)
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
    messages = _inject_workspace_verify_hints(messages, workspace)
    if agent_id in ("coding", "coding_plan"):
        try:
            _knowledge_snip = build_knowledge_orchestration_snippet(tenant_id=cfg_tid)
            if _knowledge_snip:
                messages = _append_system_block(messages, _knowledge_snip)
        except Exception:
            logger.debug("knowledge orchestration prompt skipped", exc_info=True)

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
        context_prep_meta=context_prep_meta,
        compaction_attempt=compaction_attempt,
        context_budget=_context_budget,
        smart_route_reason=smart_route_reason,
        attempts=attempts,
        llm_backend=llm_backend,
        harness_profile_token=_harness_prof_tok,
    )


__all__ = ["ChatTurnPreparation", "prepare_chat_turn"]
