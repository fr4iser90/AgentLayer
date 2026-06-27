"""Tool I/O, transcript, workspace setup, LLM transport."""
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
    apply_repetition_guard_to_completion,
    dashboard_db,
    db,
    external_llm_should_failover,
    http_post_chat_completions,
    llm_slot_async,
    llm_chat_transport,
    memory_api,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
    stream_chat_completions_aggregate,
    unpack_llm_attempt,
)
from apps.backend.application.agent_runtime.use_cases.auto_workspace import (
    _REPO_GIT_INTENT_RE,
    coding_repo_intent as _coding_repo_intent,
    extract_https_git_url as _extract_https_git_url,
    is_elevated_admin as _is_elevated_admin,
    try_auto_create_workspace_from_git_url as _try_auto_create_workspace_from_git_url,
    user_defers_git_workspace_to_tool as _user_defers_git_workspace_to_tool,
)
from apps.backend.application.agent_runtime.use_cases.media_events import media_play_websocket_event
from apps.backend.application.agent_runtime.use_cases.workspace_bind import (
    apply_workspace_tool_bind_side_effects as _apply_workspace_tool_bind_side_effects,
    format_workspace_verify_recap as _format_workspace_verify_recap,
    workspace_tool_bound_workspace_id as _workspace_tool_bound_workspace_id,
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
from apps.backend.domain.model_routing.resolution import (
    ModelRoutingSettings,
    profile_default_model_id,
    resolve_effective_model,
)
from apps.backend.domain.model_routing.smart_route import decide_smart_backend
from apps.backend.domain.agent_runtime.persona import _append_system_block, apply_user_persona_system

logger = logging.getLogger(__name__)

from apps.backend.application.agent_runtime.runtime.prompts import (  # noqa: E402
    WorkspaceAccessDenied,
    _tool_spec_name,
    _tools_payload_json_chars,
)


from apps.backend.domain.agent_runtime.tool_call_parsing import (  # noqa: E402
    _CONTENT_META_TOOL_NAMES,
    _CONTENT_META_TOP_LEVEL_ARG_KEYS,
    _coerce_params_dict,
    _extract_first_json_object,
    _format_normalized_tool_args_for_recap,
    _known_tool_names,
    _merge_meta_tool_obj_args,
    _parse_named_parenthesized_tool_call,
    _parse_parenthesized_tool_call,
    _parse_tool_arguments,
    _parse_tool_intent_from_content,
    _resolve_meta_tool_name,
    _resolve_tool_factory_name,
    _strip_model_output_markers,
    _text_blobs_from_message,
    _unwrap_fenced_json,
)


def _apply_tool_prefetch(
    messages: list[dict[str, Any]],
    prefetch: dict[str, Any],
    *,
    create_tool_max_bytes: int = 120_000,
) -> None:
    args = {
        k: prefetch[k]
        for k in ("filename", "registered_tool_name", "tool_name", "name")
        if k in prefetch and prefetch[k] is not None and str(prefetch[k]).strip()
    }
    if not args:
        return
    snippet = execute_tool(_resolve_tool_factory_name("read"), args)
    try:
        o = json.loads(snippet)
    except json.JSONDecodeError:
        o = {}
    if isinstance(o, dict) and o.get("ok") is True:
        src = str(o.get("source") or "")
        max_c = min(len(src), create_tool_max_bytes)
        block = (
            "Server prefetch via read_tool — edit this **extra-tool module** with read_tool/update_tool/replace_tool "
            "(not fs_* local disk tools — those edit paths on the agent host/container).\n\n"
            f"File: `{o.get('filename')}`\n\n```python\n{src[:max_c]}\n```"
        )
    else:
        err = o.get("error") if isinstance(o, dict) else snippet[:500]
        block = f"Server prefetch read_tool failed: {err}"
    if not messages:
        messages.append({"role": "system", "content": block})
        return
    if messages[0].get("role") == "system":
        prev = messages[0].get("content") or ""
        messages[0] = {
            **messages[0],
            "content": (block + "\n\n" + prev).strip() if prev else block,
        }
    else:
        messages.insert(0, {"role": "system", "content": block})


def _names_from_tool_list(tools: list[Any]) -> set[str]:
    return {n for t in tools if (n := _tool_spec_name(t))}


def _extract_tool_calls_from_completion_response(
    data: dict[str, Any],
    *,
    allowed_tool_names: set[str],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]] | None, bool]:
    """
    Parse choices[0].message for wire-format ``tool_calls`` only (no prose fallback).
    """
    choice0 = (data.get("choices") or [{}])[0]
    if not isinstance(choice0, dict):
        choice0 = {}
    raw_msg = choice0.get("message")
    if not isinstance(raw_msg, dict):
        raw_msg = {}
    msg = dict(raw_msg)
    raw_tc = msg.get("tool_calls")
    had_native_tool_calls = isinstance(raw_tc, list) and len(raw_tc) > 0
    tool_calls = raw_tc if had_native_tool_calls else None
    return choice0, msg, tool_calls, had_native_tool_calls


def _approx_text_chars_in_messages(messages: list[dict[str, Any]]) -> int:
    return sum(sum(len(b) for b in _text_blobs_from_message(m)) for m in messages)


def _redact_secrets_for_log(s: str) -> str:
    """Best-effort masking for log previews (OpenWeather appid, Bearer tokens)."""
    s = re.sub(r"(?i)appid=[A-Za-z0-9._-]+", "appid=***", s)
    s = re.sub(r"(?i)bearer\s+[A-Za-z0-9._-]+", "Bearer ***", s)
    return s


def _redact_provider_error_text_for_log(raw: str | None, *, max_len: int = 500) -> str:
    """Truncate and redact LLM/HTTP provider error bodies before logging (not for clients)."""
    if not raw:
        return "(empty)"
    s = raw.strip().replace("\r\n", "\n")
    if len(s) > max_len:
        s = s[:max_len] + "…"
    s = _redact_secrets_for_log(s)
    s = re.sub(r"(?i)\bsk-[a-z0-9]{10,}\b", "sk-***", s)
    s = re.sub(r"(?i)\bxox[baprs]-[a-z0-9-]{8,}\b", "xox***", s)
    s = re.sub(r"(?i)(api[_-]?key|client_secret)\s*[:=]\s*[^\s&,\"']+", r"\1=<redacted>", s)
    return s


def _short_run_id(run_id: str | None) -> str:
    if not run_id:
        return "-"
    s = str(run_id).strip()
    return s[:8] if len(s) >= 8 else s


def _log_agent_tools_pipeline(
    *,
    agent_run_id: str | None,
    agent_id: str | None,
    allowlist_count: int,
    pre_rank_count: int,
    rank_pool_count: int,
    ranked_count: int,
    pinned_count: int,
    forward_count: int,
    tools_full_schema: bool,
    routed_category: str | None,
    forward_names: list[str],
    tools_for_request: list[Any],
    log_enabled: bool = True,
) -> None:
    if not log_enabled:
        return
    schema_mode = "full" if tools_full_schema else "catalog"
    rank_part = (
        f"rank={rank_pool_count}→{ranked_count}"
        if rank_pool_count != ranked_count
        else f"rank={rank_pool_count}"
    )
    pin_part = f"+pin{pinned_count}" if pinned_count else ""
    size_part = ""
    if tools_for_request:
        size_part = f" json~{_tools_payload_json_chars(tools_for_request)}"
    cat = routed_category or "full"
    names_bit = ""
    if forward_names and len(forward_names) <= 24:
        names_bit = f" names={forward_names}"
    elif forward_names:
        names_bit = f" names={forward_names[:12]}…+{len(forward_names) - 12}"
    logger.info(
        "tools_pipeline run_id=%s agent=%s allowlist=%d→built=%d(%s)→%s%s→llm=%d cats=%s%s%s",
        _short_run_id(agent_run_id),
        agent_id or "-",
        allowlist_count,
        pre_rank_count,
        schema_mode,
        rank_part,
        pin_part,
        forward_count,
        cat,
        size_part,
        names_bit,
    )


def _log_llm_completion_round(
    *,
    agent_run_id: str | None,
    agent_id: str | None,
    round_i: int,
    model: Any,
    messages: list[dict[str, Any]],
    tools_for_round: list[Any],
    msg: dict[str, Any],
    choice0: dict[str, Any],
    tool_calls: list[Any] | None,
    had_native_tool_calls: bool,
    log_enabled: bool = True,
    large_context_chars: int = 120_000,
    log_tool_names_each_round: bool = False,
    assistant_preview_chars: int = 0,
) -> None:
    if not log_enabled:
        return
    ctx_msgs = len(messages)
    ctx_chars = _approx_text_chars_in_messages(messages)
    large = ""
    if ctx_chars >= large_context_chars:
        large = " LARGE_CTX"
    tools_n = len(tools_for_round or [])
    names_suffix = ""
    if log_tool_names_each_round:
        rt_names = [n for t in (tools_for_round or []) if (n := _tool_spec_name(t))]
        names_suffix = f" tool_names={rt_names}"
    synthetic_tc_from_content = bool(tool_calls) and not had_native_tool_calls
    run_bit = f"run_id={_short_run_id(agent_run_id)} agent={agent_id or '-'}"
    if tool_calls:
        call_names = [(tc.get("function") or {}).get("name") or "?" for tc in tool_calls]
        logger.info(
            "llm_round %s round=%d reply=TOOLS calls=%s tools=%d ctx_msgs=%d ctx_chars~=%d%s%s",
            run_bit,
            round_i + 1,
            call_names,
            tools_n,
            ctx_msgs,
            ctx_chars,
            large,
            names_suffix,
        )
        return
    cap = assistant_preview_chars
    blobs = list(_text_blobs_from_message(msg))
    for key in ("thought", "reasoning", "thinking"):
        v = choice0.get(key)
        if isinstance(v, str) and v.strip():
            blobs.append(v)
    joined = "\n".join(blobs)
    any_text = bool(joined.strip())
    preview_len = len(joined.strip())
    if cap > 0:
        preview_note = f"preview={cap}ch"
    elif any_text:
        preview_note = f"preview_len={preview_len}ch"
    else:
        preview_note = "preview=empty"
    if not any_text:
        logfn = logger.warning if tools_n else logger.info
        logfn(
            "llm_round %s round=%d reply=empty_text tools=%d ctx_msgs=%d ctx_chars~=%d%s%s",
            run_bit,
            round_i + 1,
            tools_n,
            ctx_msgs,
            ctx_chars,
            large,
            names_suffix,
        )
        return
    logger.info(
        "llm_round %s round=%d reply=TEXT tools=%d ctx_msgs=%d ctx_chars~=%d %s%s%s",
        run_bit,
        round_i + 1,
        tools_n,
        ctx_msgs,
        ctx_chars,
        preview_note,
        large,
        names_suffix,
    )


def _normalize_workspace_id_for_gate(workspace_id: Any) -> str | None:
    if workspace_id is None:
        return None
    if isinstance(workspace_id, str):
        s = workspace_id.strip()
        return s or None
    return str(workspace_id).strip() or None


def _raise_if_workspace_inaccessible(
    *,
    workspace_id: Any,
    user_id: Any,
    workspace: dict[str, Any] | None,
    agent_id: str | None,
) -> None:
    """Fail closed: never run coding tools with a client-supplied id we did not resolve."""
    wid = _normalize_workspace_id_for_gate(workspace_id)
    if wid and user_id and workspace is None:
        raise WorkspaceAccessDenied(
            "workspace_id is not available to this user (missing, not ready, or access denied)."
        )
    aid = (agent_id or "").strip() or None
    strict = False
    if aid:
        ag = get_agent_registry().get_agent(aid)
        if ag:
            strict = bool(ag.get("strict_workspace"))
    if strict and workspace is None:
        raise WorkspaceAccessDenied(
            f"{aid} requires a workspace_id that resolves to an accessible project workspace."
        )


def _attach_speech_text_to_completion(data: dict[str, Any]) -> dict[str, Any]:
    """When web voice output is enabled, add a TTS-friendly ``speech_text`` field."""
    if not isinstance(data, dict):
        return data
    try:
        from apps.backend.domain.shared.identity import get_identity
        from apps.backend.domain.voice import voice_policy
        from apps.backend.domain.voice.speech_prep import prepare_speech_text

        _tid, uid = get_identity()
        if uid is None or not voice_policy.effective_voice_output(user_id=uid, channel="web"):
            return data
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return data
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return data
        msg = ch0.get("message")
        if not isinstance(msg, dict):
            return data
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            return data
        speech = prepare_speech_text(
            content,
            language=voice_policy.effective_stt_language(uid),
        )
        if speech:
            data["speech_text"] = speech
    except Exception:
        import logging

        logging.getLogger(__name__).debug("speech_text attach failed", exc_info=True)
    return data


def _completion_attach_agent_run_id(
    data: dict[str, Any],
    agent_run_id: str,
    *,
    context_meta: dict[str, Any] | None = None,
    run_persisted: bool | None = None,
    run_persist_warnings: list[str] | None = None,
) -> dict[str, Any]:
    if isinstance(data, dict):
        from apps.backend.domain.agent_runtime.assistant_display import prepare_completion_assistant_for_client

        data = prepare_completion_assistant_for_client(data)
        data = _attach_speech_text_to_completion(data)
        if agent_run_id and (run_persisted is None or run_persisted):
            data["agent_run_id"] = agent_run_id
        meta = dict(context_meta or {})
        if run_persisted is not None:
            meta["run_persisted"] = run_persisted
        if run_persist_warnings:
            meta["run_persist_warnings"] = list(run_persist_warnings)
        if meta:
            data["agentlayer_context"] = meta
    return data


async def _async_iter_chat_completion_sse(
    attempts_seq: list[tuple[str, dict[str, str], str, str]],
    payload_base: dict[str, Any],
    *,
    llm_backend: str,
    profile_key: str,
    timeout: float | None = None,
    model_routing_settings: ModelRoutingSettings | None = None,
) -> AsyncIterator[bytes]:
    """
    OpenAI-compatible POST with ``stream: true``; yield raw response bytes (typically SSE) from the first
    successful endpoint, with the same external failover / local 429 fallback behaviour as blocking calls.
    """
    attempts_local = list(attempts_seq)
    lb = llm_backend
    outer_profile = profile_key
    timeout_cfg = (
        None if timeout is None else httpx.Timeout(timeout, connect=120.0)
    )
    while True:
        last_http: tuple[int, str, str] | None = None  # status, body, url
        last_trans: httpx.RequestError | None = None
        async with httpx.AsyncClient(timeout=timeout_cfg) as client:
            for attempt in attempts_local:
                b_url, b_headers, b_model, b_provider = unpack_llm_attempt(attempt)
                pl: dict[str, Any] = dict(payload_base)
                pl["stream"] = True
                pl["model"] = b_model
                h = dict(b_headers) if b_headers else {"Content-Type": "application/json"}
                try:
                    async with llm_slot_async(b_provider or None):
                        async with client.stream("POST", b_url, json=pl, headers=h) as resp:
                            if resp.status_code >= 400:
                                err_body = (await resp.aread()).decode("utf-8", errors="replace")
                                if lb == "provider_db" and external_llm_should_failover(resp.status_code):
                                    logger.warning(
                                        "LLM stream: external status=%s; trying next endpoint url=%s",
                                        resp.status_code,
                                        b_url,
                                    )
                                    last_http = (resp.status_code, err_body, b_url)
                                    continue
                                err_red = _redact_provider_error_text_for_log(err_body, max_len=600)
                                logger.error(
                                    "LLM stream failed (%s): status=%s url=%s body=%s",
                                    lb,
                                    resp.status_code,
                                    b_url,
                                    err_red,
                                )
                                resp.raise_for_status()
                            async for chunk in resp.aiter_raw():
                                if chunk:
                                    yield chunk
                    return
                except httpx.HTTPStatusError:
                    raise
                except httpx.RequestError as e:
                    last_trans = e
                    logger.warning(
                        "LLM stream transport error (%s) url=%s model=%s: %s",
                        lb,
                        b_url,
                        b_model,
                        e,
                    )
                    continue
        if last_trans is not None and last_http is None:
            raise last_trans
        if last_http is not None:
            st, txt, url = last_http
            if st == 429 and lb == "provider_db":
                local_model = profile_default_model_id(outer_profile, model_routing_settings)
                attempts_local, lb = llm_chat_transport(
                    local_model,
                    outer_profile,
                    False,
                    backend_override="provider",
                    catalog_owned_by=None,
                )
                logger.warning(
                    "LLM stream: external 429; falling back to local catalog provider llm_model_id=%s",
                    local_model,
                )
                continue
            err_red = _redact_provider_error_text_for_log(txt, max_len=600)
            logger.error(
                "LLM stream failed (%s): status=%s url=%s body=%s",
                lb,
                st,
                url,
                err_red,
            )
            req = httpx.Request("POST", url)
            raise httpx.HTTPStatusError(
                f"HTTP {st}",
                request=req,
                response=httpx.Response(st, request=req, text=txt[:8000]),
            )
        raise RuntimeError("LLM stream: no chat/completions attempts")


__all__ = [
    '_CONTENT_META_TOOL_NAMES',
    '_CONTENT_META_TOP_LEVEL_ARG_KEYS',
    '_REPO_GIT_INTENT_RE',
    '_apply_tool_prefetch',
    '_apply_workspace_tool_bind_side_effects',
    '_approx_text_chars_in_messages',
    '_async_iter_chat_completion_sse',
    '_coding_repo_intent',
    '_coerce_params_dict',
    '_completion_attach_agent_run_id',
    '_extract_first_json_object',
    '_extract_https_git_url',
    '_extract_tool_calls_from_completion_response',
    '_format_normalized_tool_args_for_recap',
    '_format_workspace_verify_recap',
    '_is_elevated_admin',
    '_known_tool_names',
    '_log_agent_tools_pipeline',
    '_log_llm_completion_round',
    'media_play_websocket_event',
    '_merge_meta_tool_obj_args',
    '_names_from_tool_list',
    '_normalize_workspace_id_for_gate',
    '_parse_named_parenthesized_tool_call',
    '_parse_parenthesized_tool_call',
    '_parse_tool_arguments',
    '_parse_tool_intent_from_content',
    '_raise_if_workspace_inaccessible',
    '_redact_provider_error_text_for_log',
    '_redact_secrets_for_log',
    '_resolve_meta_tool_name',
    '_resolve_tool_factory_name',
    '_short_run_id',
    '_strip_model_output_markers',
    '_text_blobs_from_message',
    '_try_auto_create_workspace_from_git_url',
    '_unwrap_fenced_json',
    '_workspace_tool_bound_workspace_id',
]
