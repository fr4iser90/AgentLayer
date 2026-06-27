"""Tool ranking, guards, arguments, registry helpers."""
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

from apps.backend.application.agent_runtime.dependencies import (
    agent_config_effective,
    apply_repetition_guard_to_completion,
    dashboard_db,
    embed_one,
    external_llm_should_failover,
    http_post_chat_completions,
    llm_chat_transport,
    memory_api,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
    stream_chat_completions_aggregate,
)
from apps.backend.domain.shared.identity import get_identity
from apps.backend.domain.agent_runtime.registry import get_agent_registry
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.plugin_system.capability_index import filter_merged_tools_by_capabilities
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories,
    filter_merged_tools_by_domain,
    last_user_text,
)
from apps.backend.domain.scheduling.run_context import record_schedule_abort, record_schedule_tool_event
from apps.backend.domain.tools.executor import execute_tool
from apps.backend.domain.tools.invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)
from apps.backend.domain.model_routing.resolution import profile_default_model_id, resolve_effective_model
from apps.backend.domain.model_routing.smart_route import decide_smart_backend
from apps.backend.domain.agent_runtime.persona import _append_system_block, apply_user_persona_system

logger = logging.getLogger(__name__)

_DEFAULT_TOOLS_RANKING_ENABLED = True
_DEFAULT_AGENT_LOG_TOOL_PIPELINE = True
_DEFAULT_HTTP_ERROR_RECOVERY_HINTS = True

from apps.backend.application.agent_runtime.runtime.io import (  # noqa: E402
    _extract_first_json_object,
    _format_normalized_tool_args_for_recap,
    _parse_named_parenthesized_tool_call,
    _parse_tool_arguments,
    _text_blobs_from_message,
)
from apps.backend.application.agent_runtime.runtime.prompts import (  # noqa: E402
    AgentChatCancelled,
    WorkspaceAccessDenied,
    _tool_spec_name,
)

# =============================================================================
# Tool Ranking System (Phase 1: Semantic Search based)
# =============================================================================

# Tool Embedding Cache (computed once, cached in memory)
_tool_embedding_cache: dict[str, list[float]] = {}
_tool_embedding_loaded = False


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _get_tool_description(tool_spec: dict[str, Any]) -> str:
    """Extract description from tool spec."""
    func = tool_spec.get("function", {})
    return func.get("description", "") or ""


# Survive category router + semantic top-N when an agent allowlists them (e.g. coding + SSC).
_AGENT_CREDENTIAL_TOOL_NAMES = frozenset(
    {
        "save_user_secret",
        "register_secrets",
        "request_user_secret",
        "secrets_help",
        "user_secrets_status",
    }
)
# Always forwarded to the LLM when the agent allowlists them (ranking would drop them otherwise).
_AGENT_GIT_NETWORK_TOOL_NAMES = frozenset(
    {
        "git_push",
        "git_sync",
    }
)
_CODING_READ_TOOL_PINS = frozenset(
    {
        "read_file",
        "search",
        "glob",
        "list_dir",
        "retrieve_context",
    }
)
_SECURITY_AUDITOR_READ_PINS = frozenset(
    {
        "read_file",
        "search",
        "glob",
        "list_dir",
        "retrieve_context",
        "git_read",
        "findings",
        "resolve",
        "start",
        "status",
    }
)


def _partition_tool_specs_by_name(
    tools: list[Any], pin_names: frozenset[str]
) -> tuple[list[Any], list[Any]]:
    pinned: list[Any] = []
    rest: list[Any] = []
    for spec in tools:
        n = _tool_spec_name(spec)
        if n is not None and n in pin_names:
            pinned.append(spec)
        else:
            rest.append(spec)
    return pinned, rest


def _credential_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    if not agent_id or not str(agent_id).strip():
        return frozenset()
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return frozenset()
    allowed = frozenset(ag.get("tool_names") or [])
    return _AGENT_CREDENTIAL_TOOL_NAMES & allowed


def _git_network_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    if not agent_id or not str(agent_id).strip():
        return frozenset()
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return frozenset()
    allowed = frozenset(ag.get("tool_names") or [])
    return _AGENT_GIT_NETWORK_TOOL_NAMES & allowed


def _pinned_tools_for_agent(agent_id: str | None) -> frozenset[str]:
    if not agent_id or not str(agent_id).strip():
        return frozenset()
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return frozenset()
    return frozenset(str(x).strip() for x in (ag.get("pinned_tools") or []) if str(x).strip())


_RELEVANCE_MIN_SCORE = 0.10
_TRIGGER_BOOST = 0.12
_NAME_IN_TEXT_BOOST = 0.18


def _tool_name_in_user_text(tool_id: str, user_text: str) -> bool:
    tid = (tool_id or "").strip().lower()
    if not tid:
        return False
    tl = user_text.lower()
    if tid in tl:
        return True
    spaced = tid.replace("_", " ")
    return spaced in tl and spaced != tid


def _introspection_specs(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        t
        for t in tools
        if (n := _tool_spec_name(t)) is not None and n in TOOL_INTROSPECTION
    ]


def rank_tools_for_forward(
    tools: list[dict[str, Any]],
    user_input: str,
    tool_triggers: dict[str, tuple[str, ...]],
    *,
    category_routed: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    """
    Rank tools by user intent and return only forward candidates.

    Always keeps introspection tools (discovery). Action tools need semantic relevance,
    a domain trigger match, or an explicit name mention in the user message — never the
    full allowlist when nothing matches.
    """
    if (
        not agent_config_effective.effective_bool(
            "tool_forward.ranking_enabled",
            default=_DEFAULT_TOOLS_RANKING_ENABLED,
        )
        or not user_input
        or not tools
    ):
        return list(tools), False

    intro = _introspection_specs(tools)

    try:
        user_emb = embed_one(user_input)
    except Exception as e:
        logger.warning("Tool ranking: failed to get user embedding: %s", e)
        return intro or list(tools), False

    global _tool_embedding_loaded
    tools_to_embed: list[tuple[str, str]] = []
    for tool in tools:
        tool_id = tool.get("function", {}).get("name", "")
        if tool_id and tool_id not in _tool_embedding_cache:
            desc = _get_tool_description(tool)
            if desc:
                tools_to_embed.append((tool_id, desc))

    user_emb_dim = len(user_emb) if user_emb else 768
    if tools_to_embed:
        for tool_id, desc in tools_to_embed:
            try:
                emb = embed_one(desc[:2000])
                _tool_embedding_cache[tool_id] = emb
            except Exception as e:
                logger.debug("Tool ranking: failed to embed tool %s: %s", tool_id, e)
                _tool_embedding_cache[tool_id] = [0.0] * user_emb_dim

    _tool_embedding_loaded = True

    scored: list[tuple[int, float, bool]] = []
    user_input_lower = user_input.lower()
    for idx, tool in enumerate(tools):
        tool_id = tool.get("function", {}).get("name", "") or ""
        tool_emb = _tool_embedding_cache.get(tool_id)
        semantic_score = (
            _cosine_similarity(user_emb, tool_emb) if tool_emb is not None else 0.0
        )
        trigger_score = 0.0
        for trigger in tool_triggers.get(tool_id, ()):
            if trigger.lower() in user_input_lower:
                trigger_score = _TRIGGER_BOOST
                break
        name_score = _NAME_IN_TEXT_BOOST if _tool_name_in_user_text(tool_id, user_input) else 0.0
        final_score = semantic_score + trigger_score + name_score
        is_relevant = (
            final_score >= _RELEVANCE_MIN_SCORE
            or trigger_score > 0.0
            or name_score > 0.0
        )
        scored.append((idx, final_score, is_relevant))

    scored.sort(key=lambda x: x[1], reverse=True)

    if category_routed:
        ranked = [tools[i] for i, _, _ in scored]
        max_score = scored[0][1] if scored else 0.0
        logfn = logger.debug if _DEFAULT_AGENT_LOG_TOOL_PIPELINE else logger.info
        logfn(
            "Tool forward rank (category routed): %d tools (max_score=%.3f)",
            len(ranked),
            max_score,
        )
        return ranked, True

    seen: set[str] = set()
    out: list[dict[str, Any]] = []

    def _append(spec: dict[str, Any]) -> None:
        n = _tool_spec_name(spec)
        if n and n not in seen:
            out.append(spec)
            seen.add(n)

    for idx, _, _ in scored:
        n = _tool_spec_name(tools[idx])
        if n and n in TOOL_INTROSPECTION:
            _append(tools[idx])
    for idx, _, is_relevant in scored:
        n = _tool_spec_name(tools[idx])
        if not n or n in TOOL_INTROSPECTION:
            continue
        if is_relevant:
            _append(tools[idx])

    if not out:
        out = intro

    max_score = scored[0][1] if scored else 0.0
    logfn = logger.debug if _DEFAULT_AGENT_LOG_TOOL_PIPELINE else logger.info
    logfn(
        "Tool forward gate: %d/%d tools (max_score=%.3f, introspection=%d)",
        len(out),
        len(tools),
        max_score,
        sum(1 for t in out if (_tool_spec_name(t) or "") in TOOL_INTROSPECTION),
    )
    return out, True


def _rank_tools_by_user_input(
    tools: list[dict[str, Any]],
    user_input: str,
    tool_triggers: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """Deprecated alias — use ``rank_tools_for_forward``."""
    ranked, _ = rank_tools_for_forward(tools, user_input, tool_triggers)
    return ranked


# =============================================================================
# Extra system text from ``dashboard.data._agentlayer`` (see dashboard settings UI).
from apps.backend.application.agent_runtime.runtime.dashboard_tool_policy import (  # noqa: E402
    _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS,
    _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN,
    _dashboard_data_agent_instructions,
    _dashboard_data_tool_allowlist,
    _dashboard_tool_allowlist_from_request_context,
)


async def _thread_with_cancel(
    cancel_event: asyncio.Event | None,
    func: Callable[..., Any],
    /,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Run blocking work in a thread; abort promptly when ``cancel_event`` is set.

    Still waits for the worker to finish when cancelled so per-provider LLM slots
    is released before returning.
    """
    if cancel_event is None:
        return await asyncio.to_thread(func, *args, **kwargs)
    worker = asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    watcher = asyncio.create_task(cancel_event.wait())
    try:
        done, _pending = await asyncio.wait(
            {worker, watcher}, return_when=asyncio.FIRST_COMPLETED
        )
        if watcher in done and cancel_event.is_set():
            try:
                await worker
            except Exception:
                pass
            raise AgentChatCancelled()
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass
        return await worker
    finally:
        if not worker.done():
            pass


from apps.backend.domain.agent_runtime.tool_schema import (  # noqa: E402
    PLANNER_NO_EXTRA_HINTS_AFTER_TOOL,
    _args_effectively_empty,
    _infer_tool_args_from_message,
    _lookup_tool_parameter_schema,
    _normalize_tool_call_arguments,
    _registry_tool_spec_by_registered_name,
    _tool_error_suggests_incomplete_arguments,
    _tool_parameter_recovery_hint,
    _tool_schema_names_match,
    _unwrap_tool_args_aliases,
    format_tool_call_validation_error,
    tool_call_warrants_full_schema_promotion,
    validate_tool_call_arguments,
)


def _http_error_recovery_hint(tool_name: str, result: str) -> str | None:
    if not _DEFAULT_HTTP_ERROR_RECOVERY_HINTS:
        return None
    if len(result) > 8000:
        return None
    rl = result.lower()
    markers = (
        "http error",
        "bad request",
        "401 unauthorized",
        "403 forbidden",
        "404 not found",
        " 400 ",
        "'400'",
        '"400"',
        "status 400",
        "status 401",
        "status 403",
        "status 404",
        "httpx",
        "for url 'http",
        'for url "http',
    )
    if not any(m in rl for m in markers):
        return None
    fix_strategy = (
        "For a **one-line API fix** (wrong query param, URL), **`update`** is usually enough; "
        "use **`replace`** if you need a larger rewrite. "
    )
    return (
        "The previous tool output suggests an HTTP/API failure. "
        "Do not blame the API key first: **400 Bad Request** often means **wrong query parameters** "
        "(e.g. OpenWeather `/data/2.5/weather` expects **`q`** for the place name, not `city`). "
        "**401** more often means an invalid or missing key. "
        + fix_strategy
        + "Next steps: (1) **`read`** the `.py` for this tool (use `registered_tool_name` "
        f"{tool_name!r} or `filename`). (2) Optionally **`search`** for the vendor's current API docs. "
        "(3) Apply the fix with **`replace`** and/or **`update`**; use **`https://`**. "
        "(4) Or delegate to built-ins: **`invoke_registered_tool`**(`\"openweather_current\"`, "
        "`{\"location\": \"…\"}`) / `forecast` from Python in an extra tool."
    )


from apps.backend.domain.agent_runtime.tool_loop_policy import (  # noqa: E402
    _agent_final_round_text_only_hint,
    _agent_near_max_tool_rounds_reminder,
    _agent_tool_budget_system_message,
    _rewrite_delegatable_agent_tool_alias,
)


from apps.backend.domain.agent_runtime.tool_transcript import (  # noqa: E402
    _ROUNDS_DIGEST_HEADER,
    _TOOL_RECAP_HEADER,
    _agent_session_tool_recap_system_message,
    _assistant_plain_text_from_message,
    _build_client_tool_context_markdown,
    _build_llm_tool_rounds_digest,
    _build_tool_transcript_recap,
    _client_reply_is_only_server_tool_context_prefix,
    _merge_deterministic_tool_recap_into_final_completion,
    _summarize_tool_json_body,
    _tool_call_id_to_args_recap_line,
    _tool_call_id_to_name_map,
)


from apps.backend.domain.agent_runtime.loop_guards import (  # noqa: E402
    _AGENT_TOOL_DOOM_FORCE_TEXT,
    _AGENT_TOOL_DOOM_LOOP_HINT,
    _AGENT_TOOL_THRASH_FORCE_TEXT,
    _AGENT_TOOL_THRASH_HINT,
    _agent_final_text_looks_like_placeholder_tool_markup,
    _agent_tool_doom_loop_tick,
    _agent_tool_thrash_tick,
    _emit_secret_prompt_from_tool_result,
    _sanitize_final_completion_assistant_content,
    _strip_prose_fake_tool_markup,
    _synthetic_final_llm_http_error_completion,
    _tool_result_followup_hint,
    _tool_result_summary,
)


# Client-only keys: never forward to the upstream chat API.
_BODY_KEYS_STRIP_FROM_LLM = frozenset(
    {
        "tool_prefetch",
        "agent_router_categories",
        "TOOL_DOMAIN",
        "agent_pause_between_rounds",
        "agent_disabled_tools",
        "agent_plain_completion",
        "agent_capability_hints",
        "agent_capability_confirm",
        "agent_max_tool_rounds",
        "agent_llm_backend",
        "agent_tool_name_allowlist",
        "agent_id",
        "agent_parent_run_id",
        "agent_permission_ask",
        "agent_unattended",
        "agent_stream_llm",
    }
)


# **Ask** before destructive workspace tools (Plan + Build on WebSocket when ``agent_permission_ask``).
_CODING_TOOLS_PERMISSION_ASK = frozenset(
    {
        "bash",
        "git_sync",
        "write_file",
        "edit",
        "apply_patch",
        "replace",
    }
)

__all__ = [
    '_AGENT_CREDENTIAL_TOOL_NAMES',
    '_AGENT_GIT_NETWORK_TOOL_NAMES',
    '_AGENT_TOOL_DOOM_FORCE_TEXT',
    '_AGENT_TOOL_DOOM_LOOP_HINT',
    '_AGENT_TOOL_THRASH_FORCE_TEXT',
    '_AGENT_TOOL_THRASH_HINT',
    '_BODY_KEYS_STRIP_FROM_LLM',
    '_CODING_READ_TOOL_PINS',
    '_CODING_TOOLS_PERMISSION_ASK',
    'PLANNER_NO_EXTRA_HINTS_AFTER_TOOL',
    '_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS',
    '_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN',
    '_rewrite_delegatable_agent_tool_alias',
    '_ROUNDS_DIGEST_HEADER',
    '_SECURITY_AUDITOR_READ_PINS',
    '_TOOL_RECAP_HEADER',
    '_agent_final_round_text_only_hint',
    '_agent_final_text_looks_like_placeholder_tool_markup',
    '_agent_near_max_tool_rounds_reminder',
    '_agent_session_tool_recap_system_message',
    '_agent_tool_budget_system_message',
    '_agent_tool_doom_loop_tick',
    '_agent_tool_thrash_tick',
    '_assistant_plain_text_from_message',
    '_build_client_tool_context_markdown',
    '_build_llm_tool_rounds_digest',
    '_build_tool_transcript_recap',
    '_client_reply_is_only_server_tool_context_prefix',
    '_cosine_similarity',
    '_credential_tools_for_agent',
    '_dashboard_data_agent_instructions',
    '_dashboard_data_tool_allowlist',
    '_dashboard_tool_allowlist_from_request_context',
    '_emit_secret_prompt_from_tool_result',
    '_get_tool_description',
    '_git_network_tools_for_agent',
    '_http_error_recovery_hint',
    '_merge_deterministic_tool_recap_into_final_completion',
    '_normalize_tool_call_arguments',
    'validate_tool_call_arguments',
    'format_tool_call_validation_error',
    'tool_call_warrants_full_schema_promotion',
    '_partition_tool_specs_by_name',
    '_pinned_tools_for_agent',
    '_rank_tools_by_user_input',
    '_registry_tool_spec_by_registered_name',
    '_sanitize_final_completion_assistant_content',
    '_strip_prose_fake_tool_markup',
    '_summarize_tool_json_body',
    '_synthetic_final_llm_http_error_completion',
    '_thread_with_cancel',
    '_tool_call_id_to_args_recap_line',
    '_tool_call_id_to_name_map',
    '_tool_embedding_loaded',
    '_tool_parameter_recovery_hint',
    '_tool_result_followup_hint',
    '_tool_result_summary',
]
