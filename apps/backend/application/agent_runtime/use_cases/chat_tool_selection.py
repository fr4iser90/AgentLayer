from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from apps.backend.infrastructure.platform.config import config
from apps.backend.application.agent_runtime.dependencies import (
    categories_for_matches,
    db,
    gather_mcp_chat_tool_specs_async,
    policies_map,
    task_intent_strict_tools,
)
from apps.backend.application.agent_runtime.runtime.io import _log_agent_tools_pipeline
from apps.backend.application.agent_runtime.runtime.tool_loop import _dashboard_tool_allowlist_from_request_context
from apps.backend.application.agent_runtime.runtime.prompts import (
    _merge_tools,
    _parse_disabled_tool_names,
    _tool_spec_name,
)
from apps.backend.domain.plugin_system.capability_index import filter_merged_tools_by_capabilities
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories_for_agent,
    filter_merged_tools_by_domain,
)
from apps.backend.domain.agent_runtime.registry import get_agent_registry

logger = logging.getLogger(__name__)


@dataclass
class ToolSelectionResult:
    cats: frozenset[str]
    routed_category: str
    tools_for_request: list[Any]
    forward_names: list[str]
    turn_hooks: Any
    forward_plan: Any


async def select_tools_for_chat_turn(
    *,
    body: dict[str, Any],
    plain_completion: bool,
    agent_id: str | None,
    tool_domain: str | None,
    task_intent_user_text: str,
    task_intent_matches: list[Any],
    extra_cats_body: frozenset[str],
    extra_cats_hdr: frozenset[str],
    cap_hints: frozenset[str],
    cfg_tid: int | None,
    raw_tool_allow: Any,
    dashboard_ctx: Any,
    model: str | None,
    context_window_tokens: int,
    tools_ranking_enabled: bool,
    tools_full_schema: bool,
    agent_run_id: str,
    tool_context: dict[str, Any],
    router_strict_default: bool,
) -> ToolSelectionResult:
    if plain_completion:
        merged_tools: list[Any] = []
        logger.debug("chat_completion: agent_plain_completion (no tools forwarded to local provider)")
    else:
        merged_tools = _merge_tools(body.get("tools"))
    routed_category: str | None = None
    logger.debug("tool_domain before check: %r, agent_id=%r", tool_domain, agent_id)
    agent: dict[str, Any] | None = None
    agent_has_explicit_allowlist = False
    if agent_id:
        agent = get_agent_registry().get_agent(agent_id)
        if agent:
            agent_has_explicit_allowlist = bool(agent.get("tool_allowlist"))
            tool_domain_agent = agent.get("tool_domain")
            tool_names_agent = agent.get("tool_names", [])
            if tool_domain_agent and not agent_has_explicit_allowlist:
                merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain_agent)
            if tool_names_agent:
                allowed_tool_names = frozenset(tool_names_agent)
                merged_tools = [
                    t
                    for t in merged_tools
                    if (n := _tool_spec_name(t)) is None or n in allowed_tool_names
                ]
            logger.debug(
                "agent %s: %d tools after allowlist (domain=%s, explicit_names=%s)",
                agent_id,
                len(merged_tools),
                tool_domain_agent,
                bool(tool_names_agent),
            )
        else:
            logger.warning("agent_id %r not found in registry, falling back to tool_domain", agent_id)
    elif tool_domain:
        merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain)
    cats = classify_user_tool_categories(task_intent_user_text)
    cats = cats | categories_for_matches(task_intent_matches)
    cats = cats | extra_cats_body | extra_cats_hdr
    merged_tools = filter_merged_tools_by_categories_for_agent(
        merged_tools,
        cats,
        agent_has_explicit_allowlist=agent_has_explicit_allowlist,
    )
    if cap_hints:
        merged_tools = filter_merged_tools_by_capabilities(
            merged_tools,
            cap_hints,
            tools_meta=get_registry().tools_meta,
        )
    if cats:
        routed_category = (
            next(iter(cats)) if len(cats) == 1 else "+".join(sorted(cats))
        )
    elif router_strict_default:
        routed_category = "minimal"
    else:
        routed_category = "full"

    if task_intent_strict_tools(tenant_id=cfg_tid) and tool_context.get("task_intent_overlay", {}).get("tools"):
        pinned_names: set[str] = set()
        if agent:
            pinned_names.update(
                str(x).strip().lower()
                for x in (agent.get("pinned_tools") or [])
                if str(x).strip()
            )
        strict_names = {
            str(x).strip().lower()
            for x in tool_context["task_intent_overlay"]["tools"]
            if str(x).strip()
        }
        strict_names.update(str(x).strip().lower() for x in TOOL_INTROSPECTION)
        strict_names.update(pinned_names)
        before_count = len(merged_tools)
        merged_tools = [
            t
            for t in merged_tools
            if (n := _tool_spec_name(t)) is None or n.strip().lower() in strict_names
        ]
        tool_context["task_intent_overlay"]["strict_tools_applied"] = True
        tool_context["task_intent_overlay"]["tool_count_before_strict"] = before_count
        tool_context["task_intent_overlay"]["tool_count_after_strict"] = len(merged_tools)

    try:
        from apps.backend.domain.shared.identity import get_identity
        from apps.backend.domain.plugin_system.tool_policy import filter_chat_tool_specs

        pmap = policies_map()
        tenant_ctx, user_ctx = get_identity()
        role = db.user_role(user_ctx)
        merged_tools = filter_chat_tool_specs(
            merged_tools,
            get_registry(),
            pmap,
            role,
            int(tenant_ctx),
        )
    except Exception:
        logger.debug("operator/access tool filter skipped", exc_info=True)

    disabled_names = _parse_disabled_tool_names(body.get("agent_disabled_tools"))
    if disabled_names:
        merged_tools = [
            t
            for t in merged_tools
            if (n := _tool_spec_name(t)) is None or n not in disabled_names
        ]

    if isinstance(raw_tool_allow, list) and raw_tool_allow:
        allow_set = {str(x).strip() for x in raw_tool_allow if str(x).strip()}
        if allow_set:
            merged_tools = [
                t
                for t in merged_tools
                if (n := _tool_spec_name(t)) is None
                or n in allow_set
                or n in TOOL_INTROSPECTION
            ]

    wl = _dashboard_tool_allowlist_from_request_context(dashboard_ctx)
    if wl:
        before_ct = len(merged_tools)
        merged_tools = [
            t
            for t in merged_tools
            if (n := _tool_spec_name(t)) is None or n in wl
        ]
        if len(merged_tools) < before_ct:
            logger.info(
                "dashboard tool allowlist: tools %d -> %d",
                before_ct,
                len(merged_tools),
            )
        if not merged_tools:
            logger.warning(
                "dashboard tool allowlist left no tools after filters (allowed=%r…)",
                sorted(wl)[:24],
            )

    if (
        not plain_completion
        and agent_id
        and agent_id in config.AGENT_MCP_AGENT_IDS
    ):
        try:
            mcp_extra = await gather_mcp_chat_tool_specs_async()
            if wl is not None and mcp_extra:
                mcp_extra = [
                    t
                    for t in mcp_extra
                    if (nn := _tool_spec_name(t)) is None or nn in wl
                ]
            if mcp_extra:
                merged_tools = merged_tools + mcp_extra
                logger.info(
                    "MCP: attached %d tool specs for agent_id=%s",
                    len(mcp_extra),
                    agent_id,
                )
        except Exception:
            logger.warning("MCP tool discovery failed", exc_info=True)

    if config.AGENT_TOOLS_DENYLIST:
        deny = config.AGENT_TOOLS_DENYLIST
        merged_tools = [
            t
            for t in merged_tools
            if (n := _tool_spec_name(t)) is None or n not in deny
        ]
    tools_allowlist_count = len(merged_tools)

    ranking_user_text: str | None = None
    for msg in reversed(body.get("messages", [])):
        if msg.get("role") == "user":
            c = msg.get("content")
            ranking_user_text = c if isinstance(c, str) else None
            break

    from apps.backend.domain.agent_runtime.turn_hooks import turn_hooks_for_agent
    from apps.backend.domain.tools.forward_policy import (
        ToolForwardContext,
        apply_schema_modes_to_specs,
        build_tool_forward_plan,
    )

    turn_hooks = turn_hooks_for_agent(agent_id if isinstance(agent_id, str) else None)
    turn_hooks.prepare_tool_context(tool_context, ranking_user_text=ranking_user_text)

    forward_plan = build_tool_forward_plan(
        ToolForwardContext(
            agent_id=agent_id if isinstance(agent_id, str) else None,
            model_id=str(model or ""),
            context_window_tokens=context_window_tokens,
            user_text=ranking_user_text or "",
            tool_specs=merged_tools,
            ranking_enabled=tools_ranking_enabled,
            full_schema_preference=tools_full_schema,
            category_routed=bool(cats),
        )
    )
    tools_for_request = apply_schema_modes_to_specs(
        forward_plan.forward_specs,
        forward_plan.schema_mode_per_tool,
        default_full_schema=False,
    )
    tools_pre_rank_count = tools_allowlist_count
    tools_rank_pool_count = int(forward_plan.meta.get("rank_pool_count") or 0)
    tools_pinned_count = len(forward_plan.pins_included)
    tools_ranked_count = max(0, len(tools_for_request) - tools_pinned_count)

    forward_names = list(forward_plan.forward_names)
    if not config.AGENT_LOG_TOOL_PIPELINE and tools_for_request:
        logger.info(
            "tool forward: model=%s window=%d allowlist=%d forward=%d pins=%s",
            model,
            context_window_tokens,
            tools_allowlist_count,
            len(forward_names),
            forward_plan.pins_included,
        )
    if config.AGENT_LOG_TOOL_PIPELINE:
        _log_agent_tools_pipeline(
            agent_run_id=agent_run_id,
            agent_id=agent_id if isinstance(agent_id, str) else None,
            allowlist_count=tools_allowlist_count,
            pre_rank_count=tools_pre_rank_count,
            rank_pool_count=tools_rank_pool_count,
            ranked_count=tools_ranked_count,
            pinned_count=tools_pinned_count,
            forward_count=len(forward_names),
            tools_full_schema=tools_full_schema,
            routed_category=routed_category,
            forward_names=forward_names,
            tools_for_request=tools_for_request,
        )
    elif tools_for_request:
        logger.info(
            "forwarding %d tools in chat request (llm_model_id=%s, category=%s): %s",
            len(forward_names),
            model,
            routed_category or "full",
            forward_names,
        )
    return ToolSelectionResult(
        cats=cats,
        routed_category=routed_category or "full",
        tools_for_request=tools_for_request,
        forward_names=forward_names,
        turn_hooks=turn_hooks,
        forward_plan=forward_plan,
    )


__all__ = ["ToolSelectionResult", "select_tools_for_chat_turn"]
