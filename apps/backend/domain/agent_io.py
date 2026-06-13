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

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.api import memory as memory_api
from apps.backend.domain.agent_registry import get_agent_registry
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions
from apps.backend.infrastructure.openai_stream_aggregate import stream_chat_completions_aggregate
from apps.backend.infrastructure.stream_repetition_guard import apply_repetition_guard_to_completion
from apps.backend.domain.plugin_system.registry import get_registry
from apps.backend.dashboard import db as dashboard_db
from apps.backend.domain.plugin_system.capability_governance import parse_user_capability_confirm
from apps.backend.domain.plugin_system.capability_index import filter_merged_tools_by_capabilities
from apps.backend.domain.plugin_system.tool_routing import (
    TOOL_INTROSPECTION,
    classify_user_tool_categories,
    filter_merged_tools_by_categories,
    filter_merged_tools_by_domain,
    last_user_text,
)
from apps.backend.domain.schedule_run_context import record_schedule_abort, record_schedule_tool_event
from apps.backend.domain.tool_executor import execute_tool
from apps.backend.domain.tool_invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)
from apps.backend.domain.llm_smart_route import decide_smart_backend
from apps.backend.domain.model_routing import profile_default_model_id, resolve_effective_model
from apps.backend.domain.user_persona import _append_system_block, apply_user_persona_system
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    normalize_model_catalog_owned_by,
    smart_llm_routing_enabled,
)

logger = logging.getLogger(__name__)

from apps.backend.domain.agent_prompts import (  # noqa: E402
    WorkspaceAccessDenied,
    _AGENTS_AUTO_WORKSPACE_FROM_GIT_URL,
    _tool_spec_name,
    _tools_payload_json_chars,
)


def _parse_tool_arguments(raw: str | dict | None) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("invalid tool arguments JSON: %s", raw[:200])
        return {}


def _format_normalized_tool_args_for_recap(
    name: str, norm: dict[str, Any], *, max_len: int = 400
) -> str:
    """Single-line summary for logs/events — from plugin ``tool_step_detail`` when defined."""
    from apps.backend.domain.tool_step_label import recap_line_for_tool

    return recap_line_for_tool(name, norm, max_len=max_len)


def _unwrap_fenced_json(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if not lines:
        return t
    lines = lines[1:]
    while lines and lines[-1].strip() in ("```", ""):
        lines.pop()
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        obj, _end = JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _strip_model_output_markers(text: str) -> str:
    """
    Remove whole-line angle-bracket sentinels some models emit (e.g. Nemotron
    ``<｜begin▁of▁string>`` / ``<｜end▁of▁string>``) so ``replace_tool({...})`` prose can be parsed.
    """
    lines_out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if len(s) >= 3 and s[0] == "<" and s[-1] == ">" and "\n" not in s:
            inner = s[1:-1].lower()
            if any(
                needle in inner
                for needle in (
                    "begin",
                    "end",
                    "start",
                    "eof",
                    "eot",
                    "string",
                    "think",
                    "reasoning",
                )
            ):
                continue
        lines_out.append(line)
    return "\n".join(lines_out).strip()


def _parse_named_parenthesized_tool_call(text: str, tool_name: str) -> dict[str, Any] | None:
    """Parse ``tool_name({...})`` from assistant prose (common when wire args are ``{}``)."""
    name = (tool_name or "").strip()
    if not name:
        return None
    key = name + "("
    pos = 0
    while True:
        idx = text.find(key, pos)
        if idx < 0:
            break
        j = idx + len(key)
        while j < len(text) and text[j] in " \t\r\n":
            j += 1
        if j >= len(text) or text[j] != "{":
            pos = idx + 1
            continue
        try:
            obj, _end = JSONDecoder().raw_decode(text[j:])
        except json.JSONDecodeError:
            pos = idx + 1
            continue
        if isinstance(obj, dict):
            return obj
        pos = idx + 1
    return None


def _parse_parenthesized_tool_call(text: str) -> tuple[str, dict[str, Any]] | None:
    """
    Parse ``read_tool({...})`` / ``replace_tool({...})`` style text when the model
    does not emit native ``tool_calls`` (common with small Nemotron builds).
    """
    names = sorted(_CONTENT_META_TOOL_NAMES, key=len, reverse=True)
    for name in names:
        key = name + "("
        pos = 0
        while True:
            idx = text.find(key, pos)
            if idx < 0:
                break
            j = idx + len(key)
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j >= len(text) or text[j] != "{":
                pos = idx + 1
                continue
            try:
                obj, _end = JSONDecoder().raw_decode(text[j:])
            except json.JSONDecodeError:
                pos = idx + 1
                continue
            if isinstance(obj, dict):
                return name, obj
            pos = idx + 1
    return None


def _known_tool_names() -> set[str]:
    return {n for t in get_registry().chat_tool_specs if (n := _tool_spec_name(t))}


def _coerce_params_dict(p: Any) -> dict[str, Any] | None:
    if p is None:
        return {}
    if isinstance(p, dict):
        return p
    if isinstance(p, str):
        s = p.strip()
        if not s:
            return {}
        try:
            o = json.loads(s)
        except json.JSONDecodeError:
            return None
        return dict(o) if isinstance(o, dict) else None
    return None


def _resolve_tool_factory_name(base: str) -> str:
    from apps.backend.domain.plugin_system.registry import get_registry

    resolved = get_registry().resolve_domain_tool("tool_factory", base)
    return resolved or f"tool_factory.{base}"


def _resolve_meta_tool_name(name: str) -> str:
    """Map short tool_factory names to qualified registry names when needed."""
    if name in {"read", "replace", "create", "update", "rename", "list"}:
        return _resolve_tool_factory_name(name)
    return name


# JSON where the function name is under ``tool_name`` (Nemotron) instead of ``name`` / ``tool``.
_CONTENT_META_TOOL_NAMES = frozenset(
    {
        "read",
        "replace",
        "create",
        "update",
        "rename",
        "list",
        "list_available_tools",
        "get_tool_help",
    }
)

# Models often put filename/source at the JSON root while using "tool"/"name" instead of nested parameters.
_CONTENT_META_TOP_LEVEL_ARG_KEYS = (
    "filename",
    "registered_tool_name",
    "tool_name",
    "name",
    "source",
    "old_string",
    "new_string",
    "replace_all",
    "old_filename",
    "new_filename",
    "overwrite",
    "TOOL_DESCRIPTION",
)


def _merge_meta_tool_obj_args(name: str, obj: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    if name not in _CONTENT_META_TOOL_NAMES:
        return base
    out = dict(base)
    if isinstance(obj.get("parameters"), dict):
        out.update(obj["parameters"])
    if isinstance(obj.get("arguments"), dict):
        out.update(obj["arguments"])
    for k in _CONTENT_META_TOP_LEVEL_ARG_KEYS:
        if k in obj:
            out[k] = obj[k]
    return out


def _parse_tool_intent_from_content(content: str) -> tuple[str, dict[str, Any]] | None:
    """
    Some models emit JSON like {\"tool\": \"<name>\", \"parameters\": {...}} in message content
    instead of wire-format ``tool_calls``.
    """
    t = _strip_model_output_markers(_unwrap_fenced_json(content))
    pc = _parse_parenthesized_tool_call(t)
    if pc:
        return pc
    obj = _extract_first_json_object(t)
    if not obj:
        return None
    name: str | None = None
    params: dict[str, Any] | None = None
    tnk = obj.get("tool_name")
    if isinstance(tnk, str) and tnk.strip() in _CONTENT_META_TOOL_NAMES:
        name = tnk.strip()
        params = {k: v for k, v in obj.items() if k != "tool_name"}
        params = _merge_meta_tool_obj_args(name, obj, params)
        return name, params
    if isinstance(obj.get("tool"), str):
        name = str(obj["tool"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    elif isinstance(obj.get("name"), str):
        name = str(obj["name"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    elif isinstance(obj.get("function"), str):
        name = str(obj["function"]).strip()
        p = obj.get("parameters")
        if not isinstance(p, dict):
            p = obj.get("arguments")
        if not isinstance(p, dict):
            p = obj.get("params")
        params = _coerce_params_dict(p)
    if not name or params is None:
        return None
    if isinstance(params, dict):
        params = _merge_meta_tool_obj_args(name, obj, params)
    return name, params


def _text_blobs_from_message(msg: dict[str, Any]) -> list[str]:
    """Collect strings where models may hide JSON tool intent (reasoning models, multimodal content)."""
    blobs: list[str] = []
    t = msg.get("text")
    if isinstance(t, str) and t.strip():
        blobs.append(t)
    c = msg.get("content")
    if isinstance(c, str) and c.strip():
        blobs.append(c)
    elif isinstance(c, list):
        for part in c:
            if isinstance(part, dict):
                if part.get("type") == "text" and isinstance(part.get("text"), str):
                    blobs.append(part["text"])
                elif isinstance(part.get("content"), str):
                    blobs.append(part["content"])
            elif isinstance(part, str):
                blobs.append(part)
    for key in (
        "reasoning_content",
        "reasoning",
        "thinking",
        "thought",
        "reasoning_content_delta",  # some proxies
    ):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            blobs.append(v)
    return blobs


def _apply_tool_prefetch(messages: list[dict[str, Any]], prefetch: dict[str, Any]) -> None:
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
        max_c = min(len(src), config.CREATE_TOOL_MAX_BYTES)
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
) -> None:
    if not config.AGENT_LOG_TOOL_PIPELINE:
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
) -> None:
    if not config.AGENT_LOG_LLM_ROUNDS:
        return
    ctx_msgs = len(messages)
    ctx_chars = _approx_text_chars_in_messages(messages)
    large = ""
    if ctx_chars >= config.AGENT_LOG_LARGE_CONTEXT_CHARS:
        large = " LARGE_CTX"
    tools_n = len(tools_for_round or [])
    names_suffix = ""
    if config.AGENT_LOG_TOOL_NAMES_EACH_ROUND:
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
    cap = config.AGENT_LOG_ASSISTANT_PREVIEW_CHARS
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


_REPO_GIT_INTENT_RE = re.compile(
    r"\b(?:git\s+)?clone\b|\brep(?:ository|os?)\b|\bcodebase\b|\b(?:pull\s+request|pr)\b|"
    r"\bgit\s+init\b|\bgit\s+pull\b|\bgit\s+push\b|\bcommit(?:s)?\b|\bbranch\b|\bmerge\b|"
    r"\b(?:fork|star)\s+(?:this\s+)?(?:repo|repository)\b|\bgithub\.com/",
    re.IGNORECASE,
)


def _user_defers_git_workspace_to_tool(text: str) -> bool:
    """Prompt assigns clone/create to workspace.create — skip chat auto-clone/reuse."""
    low = (text or "").lower()
    return "workspace.create" in low and ("git_url" in low or "source=git" in low)


def _try_auto_create_workspace_from_git_url(
    *,
    agent_id: str | None,
    user_id: Any,
    user_obj: Any,
    last_user_text: str,
    embedded_subagent: bool,
) -> dict[str, Any] | None:
    """
    Admin users: clone/bind a project workspace when the last user message contains a Git HTTPS URL.
    Used for ``coding`` and ``general`` chat (not embedded sub-agents).
    """
    aid = (agent_id or "general").strip() or "general"
    if aid not in _AGENTS_AUTO_WORKSPACE_FROM_GIT_URL:
        return None
    if embedded_subagent or not user_id:
        return None
    gu = _extract_https_git_url(last_user_text)
    if not gu:
        return None
    if _user_defers_git_workspace_to_tool(last_user_text):
        return None
    u = user_obj
    if u is None:

        class UserLike:
            def __init__(self, uid: Any):
                self.id = uid
                self.role = "user"

        u = UserLike(user_id)
        try:
            from apps.backend.infrastructure.db import db as _role_db2

            u.role = _role_db2.user_role(user_id) or "user"
        except Exception:
            pass
    if u is None or not _is_elevated_admin(u, None, user_id):
        return None
    try:
        from apps.backend.domain.workspace.workspace_common import find_owned_git_workspace
        from apps.backend.infrastructure.workspace_service import (
            WorkspaceCreateError,
            create_project_workspace_for_user,
            ensure_workspace as _ensure_ws,
            slug_from_git_url,
        )

        existing = find_owned_git_workspace(u, git_url=gu)
        if existing:
            wid = str(existing.get("id") or "").strip()
            if wid:
                workspace = _ensure_ws(wid, u)
                if workspace:
                    logger.info(
                        "chat_completion: reusing owned workspace %s for Git URL (agent=%s)",
                        wid,
                        aid,
                    )
                    return workspace

        nm = f"{slug_from_git_url(gu)}-{uuid.uuid4().hex[:8]}"
        created = create_project_workspace_for_user(
            u,
            name=nm,
            source="git",
            git_url=gu,
            git_branch="main",
        )
        wid = str(created["id"])
        workspace = _ensure_ws(wid, u)
        if workspace:
            logger.info(
                "chat_completion: auto-created workspace %s from Git URL (agent=%s)",
                wid,
                aid,
            )
            return workspace
    except WorkspaceCreateError as e:
        logger.warning("auto-create workspace failed: %s", e.message)
    except Exception as e:
        logger.warning("auto-create workspace failed: %s", e)
    return None


def _extract_https_git_url(text: str) -> str | None:
    if not (text or "").strip():
        return None
    for m in re.finditer(r"https://[^\s\)\]\"'<>]+", text):
        u = m.group(0).rstrip(").,;]")
        low = u.lower()
        if low.endswith(".git"):
            return u
        for marker in (
            "github.com/",
            "gitlab.com/",
            "bitbucket.org/",
            "codeberg.org/",
        ):
            if marker in low:
                return u
        if "/git/" in low or ".git" in low:
            return u
    return None


def _coding_repo_intent(text: str) -> bool:
    if _extract_https_git_url(text):
        return True
    return bool(text and _REPO_GIT_INTENT_RE.search(text))


def _is_elevated_admin(
    user_obj: Any,
    bearer_user_role: str | None,
    user_id: Any,
) -> bool:
    if (bearer_user_role or "").strip().lower() == "admin":
        return True
    if user_obj is not None and getattr(user_obj, "role", None) == "admin":
        return True
    if user_id:
        try:
            from apps.backend.infrastructure.db import db as _role_db

            if _role_db.user_role(user_id) == "admin":
                return True
        except Exception:
            pass
    return False


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
        from apps.backend.domain.identity import get_identity
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
        from apps.backend.domain.assistant_display_sanitize import prepare_completion_assistant_for_client

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


def _workspace_tool_bound_workspace_id(tool_name: str, tool_result_json: str) -> str | None:
    """Return workspace id when ``bind`` / bound ``create`` succeeded."""
    if tool_name not in ("bind", "create", "workspace.bind", "workspace.create"):
        return None
    try:
        data = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("ok") is not True:
        return None
    if tool_name in ("create", "workspace.create") and not data.get("bound"):
        return None
    ws = data.get("workspace")
    if not isinstance(ws, dict):
        return None
    wid = ws.get("id")
    if wid is None:
        return None
    s = str(wid).strip()
    return s or None


async def _apply_workspace_tool_bind_side_effects(
    *,
    tool_name: str,
    result: str,
    tool_context: dict[str, Any],
    messages: list[dict[str, Any]],
    event_emit: Any,
    agent_run_id: str,
) -> None:
    """Refresh bootstrap snippet and notify UI after workspace_bind / workspace_create."""
    wid = _workspace_tool_bound_workspace_id(tool_name, result)
    if not wid:
        return
    ws = tool_context.get("workspace")
    if isinstance(ws, dict):
        try:
            from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
                build_retrieval_bootstrap_snippet,
                maybe_schedule_index_on_attach,
            )

            snippet = build_retrieval_bootstrap_snippet(ws)
            if snippet:
                messages.append({"role": "system", "content": snippet})
            maybe_schedule_index_on_attach(ws)
        except Exception as e:
            logger.debug("workspace bind bootstrap skipped: %s", e)
    if event_emit:
        await event_emit(
            {
                "type": "agent.session",
                "agent_run_id": agent_run_id,
                "workspace_id": wid,
                "workspace_bound": True,
            }
        )


def _format_workspace_verify_recap(tool_result_json: str) -> str | None:
    """Build a short system snippet from ``workspace_verify`` JSON output."""
    try:
        d = json.loads(tool_result_json)
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    if "verify_command" not in d and "exit_code" not in d:
        return None
    parts: list[str] = ["[Workspace verify recap]"]
    cmd = d.get("verify_command")
    if isinstance(cmd, str) and cmd.strip():
        parts.append(f"command: {cmd.strip()[:400]}")
    if d.get("ok") is not None:
        parts.append(f"ok: {bool(d.get('ok'))}")
    if "exit_code" in d:
        parts.append(f"exit_code: {d.get('exit_code')}")
    out = d.get("output")
    if isinstance(out, str) and out.strip():
        sn = out.strip()
        if len(sn) > 1200:
            sn = sn[:1200] + "…"
        parts.append("output:\n" + sn)
    err = d.get("error")
    if isinstance(err, str) and err.strip() and (not isinstance(out, str) or not out.strip()):
        parts.append("error: " + err.strip()[:800])
    return "\n".join(parts)


async def _async_iter_chat_completion_sse(
    attempts_seq: list[tuple[str, dict[str, str], str, str]],
    payload_base: dict[str, Any],
    *,
    llm_backend: str,
    profile_key: str,
    timeout: float | None = None,
) -> AsyncIterator[bytes]:
    """
    OpenAI-compatible POST with ``stream: true``; yield raw response bytes (typically SSE) from the first
    successful endpoint, with the same external failover / local 429 fallback behaviour as blocking calls.
    """
    from apps.backend.infrastructure.llm_chat_attempt import unpack_llm_attempt
    from apps.backend.infrastructure.llm_concurrency import llm_slot_async

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
                                if lb == "provider_admin" and external_llm_should_failover(resp.status_code):
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
            if st == 429 and lb == "provider_admin":
                local_model = profile_default_model_id(outer_profile)
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


def media_play_websocket_event(tool_name: str, result: str | None) -> dict[str, Any] | None:
    """When ``media_enqueue`` succeeded with ``play_now``, tell the Web UI to start the footer player."""
    if (tool_name or "").strip() != "media_enqueue" or not result:
        return None
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return None
    if payload.get("ok") is not True or not payload.get("now_playing_id"):
        return None
    item = payload.get("item")
    dash = payload.get("dashboard_id")
    qp = payload.get("queue_path")
    if not isinstance(item, dict) or not dash or not qp:
        return None
    queue = payload.get("queue")
    if not isinstance(queue, dict) or not isinstance(queue.get("items"), list):
        queue = {
            "now_playing_id": str(payload["now_playing_id"]),
            "items": [item],
            "shuffle": False,
            "repeat": "off",
        }
    return {
        "type": "agent.media_play",
        "dashboard_id": str(dash),
        "queue_path": str(qp),
        "now_playing_id": str(payload["now_playing_id"]),
        "item": item,
        "queue": queue,
    }


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
