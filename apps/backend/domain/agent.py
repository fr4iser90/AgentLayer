"""
Chat completion with tool-call loop (**Planner**): builds messages and asks the model which tools to call.

Deterministic tool execution goes through :func:`apps.domain.tool_executor.execute_tool` (**Executor**).
See ``docs/adr/0001-tool-and-agent-architecture.md``.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from json import JSONDecoder
from typing import Any, Literal

import httpx

from apps.backend.core.config import config
from apps.backend.domain.identity import get_identity
from apps.backend.api import memory as memory_api
from apps.backend.domain.agent_registry import get_agent_registry
from apps.backend.infrastructure.ollama_gate import ollama_post_chat_completions, ollama_post_json
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
from apps.backend.domain.tool_executor import execute_tool
from apps.backend.domain.tool_invocation_context import (
    bind_capability_confirmed,
    reset_capability_confirmed,
    reset_tool_invocation_messages,
    set_tool_invocation_messages,
)
from apps.backend.domain.llm_smart_route import decide_smart_backend
from apps.backend.domain.model_routing import ollama_model_for_profile, resolve_effective_model
from apps.backend.domain.user_persona import apply_user_persona_system
from apps.backend.infrastructure.operator_settings import (
    external_llm_should_failover,
    llm_chat_transport,
    smart_llm_routing_enabled,
)

logger = logging.getLogger(__name__)

# Extra system text from ``dashboard.data._agentlayer`` (see dashboard settings UI).
_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS = 8000


def _dashboard_data_agent_instructions(data: Any) -> str:
    """Return trimmed instructions from ``data._agentlayer`` (optional)."""
    if not isinstance(data, dict):
        return ""
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return ""
    raw = meta.get("system_prompt_extra")
    if raw is None:
        raw = meta.get("instructions")
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    if len(s) > _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS:
        logger.warning(
            "dashboard agent instructions truncated from %d to %d chars",
            len(s),
            _MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS,
        )
        return s[:_MAX_DASHBOARD_AGENT_INSTRUCTIONS_CHARS]
    return s


# Non-empty allowlist: only these tool function names (after policy / disabled filters).
_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN = 200


def _dashboard_data_tool_allowlist(data: Any) -> frozenset[str] | None:
    """Return allowed tool names from ``data._agentlayer.tool_allowlist`` or None if unset/empty."""
    if not isinstance(data, dict):
        return None
    meta = data.get("_agentlayer")
    if not isinstance(meta, dict):
        return None
    raw = meta.get("tool_allowlist")
    if raw is None:
        raw = meta.get("allowed_tools")
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [x.strip() for x in raw.replace(",", " ").split() if x.strip()]
        if not parts:
            return None
        names = parts
    elif isinstance(raw, list):
        names = [str(x).strip() for x in raw if isinstance(x, str) and str(x).strip()]
        if not names:
            return None
    else:
        return None
    if len(names) > _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN:
        logger.warning(
            "dashboard tool_allowlist truncated from %d to %d entries",
            len(names),
            _MAX_DASHBOARD_TOOL_ALLOWLIST_LEN,
        )
        names = names[:_MAX_DASHBOARD_TOOL_ALLOWLIST_LEN]
    return frozenset(names)


def _dashboard_tool_allowlist_from_request_context(dashboard_ctx: Any) -> frozenset[str] | None:
    if not isinstance(dashboard_ctx, dict):
        return None
    wid_s = dashboard_ctx.get("dashboard_id")
    if not isinstance(wid_s, str) or not wid_s.strip():
        return None
    try:
        wid = uuid.UUID(wid_s.strip())
    except ValueError:
        return None
    ident = get_identity()
    if ident[1] is None:
        return None
    tid, uid = ident
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return None
    return _dashboard_data_tool_allowlist(ws.get("data"))


class AgentChatCancelled(Exception):
    """Client aborted in-flight chat (e.g. WebSocket ``{"type":"cancel"}``)."""


def _registry_tool_spec_by_registered_name(name: str) -> dict[str, Any] | None:
    n = (name or "").strip()
    if not n:
        return None
    for spec in get_registry().chat_tool_specs:
        if not isinstance(spec, dict):
            continue
        fn = spec.get("function")
        if isinstance(fn, dict) and fn.get("name") == n:
            return copy.deepcopy(spec)
    return None


def _http_error_recovery_hint(tool_name: str, result: str) -> str | None:
    if not config.AGENT_TOOL_HTTP_ERROR_RECOVERY_HINTS:
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
        "For a **one-line API fix** (wrong query param, URL), **`update_tool`** is usually enough; "
        "use **`replace_tool`** if you need a larger rewrite. "
    )
    return (
        "The previous tool output suggests an HTTP/API failure. "
        "Do not blame the API key first: **400 Bad Request** often means **wrong query parameters** "
        "(e.g. OpenWeather `/data/2.5/weather` expects **`q`** for the place name, not `city`). "
        "**401** more often means an invalid or missing key. "
        + fix_strategy
        + "Next steps: (1) **`read_tool`** the `.py` for this tool (use `registered_tool_name` "
        f"{tool_name!r} or `filename`). (2) Optionally **`search_web`** for the vendor's current API docs. "
        "(3) Apply the fix with **`replace_tool`** and/or **`update_tool`**; use **`https://`**. "
        "(4) Or delegate to built-ins: **`invoke_registered_tool`**(`\"openweather_current\"`, "
        "`{\"location\": \"…\"}`) / `openweather_forecast` from Python in an extra tool."
    )


# Client-only keys: never forward to Ollama (not in upstream Chat Completions request schema).
_BODY_KEYS_STRIP_FROM_OLLAMA = frozenset(
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
    }
)


def _parse_disabled_tool_names(raw: Any) -> set[str]:
    """Client hint: tool function names to omit from this request (after policy filter)."""
    if not isinstance(raw, list):
        return set()
    return {str(x).strip() for x in raw if str(x).strip()}


def _coerce_body_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if not s:
        return default
    return s in ("1", "true", "yes", "on")


def _parse_router_category_tokens(raw: str | None) -> frozenset[str]:
    if not raw or not str(raw).strip():
        return frozenset()
    return frozenset(x.strip().lower() for x in str(raw).split(",") if x.strip())


def _parse_router_categories_value(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return _parse_router_category_tokens(raw)
    if isinstance(raw, list):
        return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
    return frozenset()


def _parse_capability_hints(raw: Any) -> frozenset[str]:
    """Client hint: filter tools to those declaring any of these capability strings (ADR 0001)."""
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset(x.strip() for x in raw.replace(",", " ").split() if x.strip())
    if isinstance(raw, list):
        return frozenset(str(x).strip() for x in raw if str(x).strip())
    return frozenset()


def _inject_agent_system_prompt(messages: list[dict[str, Any]], agent_id: str | None) -> list[dict[str, Any]]:
    """Inject agent-specific system prompt from registry."""
    if not agent_id:
        return messages
    agent = get_agent_registry().get_agent(agent_id)
    if not agent:
        logger.debug("agent %r not found, skipping system prompt injection", agent_id)
        return messages
    system_prompt = agent.get("system_prompt", "")
    if not system_prompt:
        return messages
    if not messages:
        return [{"role": "system", "content": system_prompt}]
    out = list(messages)
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + system_prompt).strip() if existing else system_prompt,
        }
    else:
        out.insert(0, {"role": "system", "content": system_prompt})
    return out


def _inject_system_prompt(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not config.SYSTEM_PROMPT_EXTRA:
        return messages
    extra = config.SYSTEM_PROMPT_EXTRA
    if not messages:
        return [{"role": "system", "content": extra}]
    out = list(messages)
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + extra).strip() if existing else extra,
        }
    else:
        out.insert(0, {"role": "system", "content": extra})
    return out


def _inject_dashboard_context(
    messages: list[dict[str, Any]], raw: Any
) -> list[dict[str, Any]]:
    """
    Optional client hint: ``agent_dashboard_context: { "dashboard_id": "<uuid>" }``.
    Resolved server-side so the model only sees dashboards the user may access.
    """
    if not isinstance(raw, dict):
        return messages
    wid_s = raw.get("dashboard_id")
    if not isinstance(wid_s, str) or not wid_s.strip():
        return messages
    try:
        wid = uuid.UUID(wid_s.strip())
    except ValueError:
        return messages
    ident = get_identity()
    if ident[1] is None:
        return messages
    tid, uid = ident
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        note = (
            "[Dashboard context] The client requested a default dashboard id but it is not "
            "accessible to this user; do not assume a dashboard id until tools return one."
        )
    else:
        k = (ws.get("kind") or "").strip()
        title = (ws.get("title") or "").strip()
        role = (ws.get("access_role") or "").strip()
        note = (
            f"[Dashboard context] The user opened this dashboard in the app. "
            f"dashboard_id={wid!s}, kind={k!r}, title={title!r}, access_role={role!r}. "
            f"For shopping_list_* tools, use this dashboard_id when the user means 'this list' "
            f"and does not clearly mean a different list; for pets_* when kind is pets, or ideas_* "
            f"when kind is ideas, use the same id. If unsure which list, call shopping_list_dashboards; "
            f"for pets boards pets_dashboards; for ideas boards ideas_dashboards."
        )
        extra = _dashboard_data_agent_instructions(ws.get("data"))
        if extra:
            note = note + "\n\n[Dashboard-specific agent instructions]\n" + extra
    out = list(messages)
    if not out:
        return [{"role": "system", "content": note}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + note).strip() if existing else note,
        }
    else:
        out.insert(0, {"role": "system", "content": note})
    return out


def _inject_user_memory_context(messages: list[dict[str, Any]], raw_dashboard_ctx: Any) -> list[dict[str, Any]]:
    """
    Inject persisted user memory (facts + semantic notes) as a system snippet.
    Writes are opt-in via tools; this is read-only retrieval.
    """
    q = (last_user_text(messages) or "").strip()
    if not q:
        return messages

    wid: uuid.UUID | None = None
    if isinstance(raw_dashboard_ctx, dict):
        wsid = raw_dashboard_ctx.get("dashboard_id")
        if isinstance(wsid, str) and wsid.strip():
            try:
                wid = uuid.UUID(wsid.strip())
            except ValueError:
                wid = None

    try:
        snippet = memory_api.render_memory_context(dashboard_id=wid, user_query=q)
    except Exception:
        snippet = ""
    if not snippet:
        return messages

    out = list(messages)
    if not out:
        return [{"role": "system", "content": snippet}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + snippet).strip() if existing else snippet,
        }
    else:
        out.insert(0, {"role": "system", "content": snippet})
    return out


def _tool_spec_name(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function")
    if isinstance(fn, dict):
        n = fn.get("name")
        return str(n) if n else None
    return None


def _merge_tools(body_tools: list[Any] | None) -> list[Any]:
    """
    Always merge the live registry tool list into the request for Ollama.

    Open WebUI often sends its own non-empty ``tools`` list; previously that
    replaced our list entirely so the model never saw agent-layer tools.
    """
    ours = get_registry().chat_tool_specs
    if not body_tools:
        return ours
    seen = {n for t in ours if (n := _tool_spec_name(t))}
    merged: list[Any] = list(ours)
    for t in body_tools:
        if not isinstance(t, dict):
            continue
        n = _tool_spec_name(t)
        if n is None:
            merged.append(t)
            continue
        if n not in seen:
            merged.append(t)
            seen.add(n)
    logger.debug(
        "tools merge: registry=%d client=%d merged=%d",
        len(ours),
        len(body_tools),
        len(merged),
    )
    return merged


_CATALOG_PARAM_HINT = (
    "Full JSON parameter schema is not inlined here. Call get_tool_help with tool_name set to this "
    "tool's name, then invoke with arguments matching that schema."
)


def _catalog_tool_function(name: str, fn: dict[str, Any]) -> dict[str, Any]:
    """Small tools[] entry: TOOL_LABEL + TOOL_DESCRIPTION hint; minimal parameters (never full domain schemas)."""
    desc = (fn.get("TOOL_DESCRIPTION") or "").strip()
    if _CATALOG_PARAM_HINT not in desc:
        desc = f"{desc}\n\n{_CATALOG_PARAM_HINT}".strip() if desc else _CATALOG_PARAM_HINT
    if name == "get_tool_help":
        params: dict[str, Any] = {
            "type": "object",
            "properties": {
                "tool_name": {
                    "type": "string",
                    "description": "Exact tool name from list_tools_in_category or list_available_tools",
                },
            },
            "required": ["tool_name"],
        }
    elif name == "list_tools_in_category":
        params = {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category id from list_tool_categories",
                },
            },
            "required": ["category"],
        }
    else:
        params = {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": params,
        },
    }


def _tools_for_chat_request(merged_tools: list[Any]) -> list[Any]:
    """
    Build tools[] for Ollama: **nur Katalog-Einträge** (Name, Kurzbeschreibung, minimale parameters).

    **Volles** JSON-Schema für ein Domänen-Tool gibt es **nicht** in ``tools[]`` — nur in der
    **Tool-Antwort** von ``get_tool_help(tool_name)`` (stufenweise Erkundung).
    """
    out: list[Any] = []
    for spec in merged_tools:
        if not isinstance(spec, dict):
            out.append(spec)
            continue
        name = _tool_spec_name(spec)
        fn = spec.get("function")
        if not name or not isinstance(fn, dict):
            out.append(spec)
            continue
        out.append(_catalog_tool_function(name, fn))
    return out


def _tools_payload_size_estimate(tools: list[Any]) -> tuple[int, int, int]:
    """
    (json_char_count, est_tokens_low, est_tokens_high) for the tools[] array as sent in the request.

    Heuristic only: chars/4 .. chars/3 — not the model tokenizer; real usage depends on the backend.
    """
    if not tools:
        return 0, 0, 0
    raw = json.dumps(tools, ensure_ascii=False, separators=(",", ":"))
    c = len(raw)
    lo = (c + 3) // 4
    hi = (c + 2) // 3
    return c, lo, hi


def _log_tools_request_estimate(TOOL_LABEL: str, tools: list[Any]) -> None:
    if not config.AGENT_LOG_TOOLS_REQUEST_ESTIMATE:
        return
    n = len(tools)
    jc, lo, hi = _tools_payload_size_estimate(tools)
    logger.info(
        "tools request %s: tool_defs=%d json_chars=%d est_tokens~%d-%d (heuristic, not tokenizer)",
        TOOL_LABEL,
        n,
        jc,
        lo,
        hi,
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


# JSON where the function name is under ``tool_name`` (Nemotron) instead of ``name`` / ``tool``.
_CONTENT_META_TOOL_NAMES = frozenset(
    {
        "read_tool",
        "replace_tool",
        "create_tool",
        "update_tool",
        "rename_tool",
        "list_tools",
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


def _content_fallback_args_acceptable(name: str, params: dict[str, Any]) -> bool:
    """Reject synthetic tool_calls that would no-op or loop (e.g. read_tool({}))."""
    if name == "read_tool":
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "replace_tool":
        if not str(params.get("source") or "").strip():
            return False
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "update_tool":
        if not str(params.get("old_string") or "").strip():
            return False
        return any(
            str(params.get(k) or "").strip()
            for k in ("filename", "registered_tool_name", "tool_name", "name")
        )
    if name == "create_tool":
        if str(params.get("source") or "").strip():
            return True
        return bool(str(params.get("tool_name") or "").strip() or str(params.get("name") or "").strip())
    if name == "rename_tool":
        return bool(str(params.get("old_filename") or "").strip()) and bool(
            str(params.get("new_filename") or "").strip()
        )
    if name == "get_tool_help":
        return bool(str(params.get("tool_name") or "").strip())
    return True


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


def _synthetic_tool_calls_from_message(
    msg: dict[str, Any],
    choice: dict[str, Any] | None = None,
    *,
    allowed_tool_names: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    if not config.CONTENT_TOOL_FALLBACK:
        return None
    if msg.get("tool_calls"):
        return None
    known = allowed_tool_names if allowed_tool_names is not None else _known_tool_names()
    blobs = _text_blobs_from_message(msg)
    if choice:
        for key in ("thought", "reasoning", "thinking"):
            v = choice.get(key)
            if isinstance(v, str) and v.strip():
                blobs.append(v)
    for blob in blobs:
        parsed = _parse_tool_intent_from_content(blob)
        if not parsed:
            continue
        name, params = parsed
        if name not in known:
            logger.debug("content tool JSON names unknown tool %r, ignoring", name)
            continue
        if not _content_fallback_args_acceptable(name, params):
            logger.info(
                "content tool fallback: reject %s with insufficient args %r (avoid empty read_tool loop)",
                name,
                params,
            )
            continue
        tc = {
            "id": f"content-{uuid.uuid4().hex[:16]}",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(params)},
        }
        logger.info(
            "content tool fallback: synthetic tool_calls for %s(%s) (JSON or parenthesized prose)",
            name,
            params,
        )
        return [tc]
    logger.debug(
        "content tool fallback: no tool JSON found (message keys=%s, blobs=%d)",
        list(msg.keys()),
        len(blobs),
    )
    return None


def _apply_tool_prefetch(messages: list[dict[str, Any]], prefetch: dict[str, Any]) -> None:
    args = {
        k: prefetch[k]
        for k in ("filename", "registered_tool_name", "tool_name", "name")
        if k in prefetch and prefetch[k] is not None and str(prefetch[k]).strip()
    }
    if not args:
        return
    snippet = execute_tool("read_tool", args)
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
    Parse choices[0].message and optional synthetic tool calls from content.
    Mutates ``data`` in place when synthetic tool_calls are applied (same as inline logic).
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
    if not tool_calls:
        tool_calls = _synthetic_tool_calls_from_message(
            msg, choice0, allowed_tool_names=allowed_tool_names
        )
        if tool_calls:
            msg["tool_calls"] = tool_calls
            choice0["message"] = msg
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


def _log_ollama_round(
    *,
    round_i: int,
    max_rounds_cap: int,
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
        large = f" LARGE_CTX(>={config.AGENT_LOG_LARGE_CONTEXT_CHARS} chars)"
    rt_names = [n for t in (tools_for_round or []) if (n := _tool_spec_name(t))]
    syn = bool(tool_calls) and not had_native_tool_calls
    if tool_calls:
        call_names = [(tc.get("function") or {}).get("name") or "?" for tc in tool_calls]
        logger.info(
            "llm round %d/%d llm_model_id=%s reply=TOOLS calls=%s content_json_fallback=%s "
            "ctx_msgs=%d ctx_text_chars~=%d ollama_tool_defs=%d tool_names=%s%s",
            round_i + 1,
            max_rounds_cap,
            model,
            call_names,
            syn,
            ctx_msgs,
            ctx_chars,
            len(rt_names),
            rt_names,
            large,
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
    if cap > 0:
        preview = _redact_secrets_for_log(joined[:cap])
    else:
        preview = "(set AGENT_LOG_ASSISTANT_PREVIEW_CHARS>0 for redacted snippet)"
    if not any_text:
        logfn = logger.warning if rt_names else logger.info
        logfn(
            "llm round %d/%d llm_model_id=%s reply=EMPTY_NO_TOOLS content_json_fallback=%s "
            "ctx_msgs=%d ctx_text_chars~=%d ollama_tool_defs=%d%s",
            round_i + 1,
            max_rounds_cap,
            model,
            syn,
            ctx_msgs,
            ctx_chars,
            len(rt_names),
            large,
        )
        return
    logger.info(
        "llm round %d/%d llm_model_id=%s reply=TEXT_NO_TOOLS content_json_fallback=%s "
        "ctx_msgs=%d ctx_text_chars~=%d ollama_tool_defs=%d preview=%r%s",
        round_i + 1,
        max_rounds_cap,
        model,
        syn,
        ctx_msgs,
        ctx_chars,
        len(rt_names),
        preview,
        large,
    )


async def chat_completion(
    body: dict[str, Any],
    *,
    router_categories_header: str | None = None,
    tool_domain_header: str | None = None,
    model_profile_header: str | None = None,
    model_override_header: str | None = None,
    bearer_user_role: str | None = None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    control_queue: asyncio.Queue | None = None,
    cancel_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    # stream flag is ignored here; Ollama always gets stream=false. Caller may wrap JSON as SSE.
    body.pop("agent_tool_mode", None)
    body.pop("agent_mode", None)
    plain_completion = _coerce_body_bool(body.pop("agent_plain_completion", None), False)
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
    _raw_max_rounds = body.pop("agent_max_tool_rounds", None)
    _raw_llm_be = body.pop("agent_llm_backend", None)
    _raw_tool_allow = body.pop("agent_tool_name_allowlist", None)
    agent_id = body.pop("agent_id", None)
    if isinstance(agent_id, str):
        agent_id = agent_id.strip() or None
    
    from apps.backend.domain.identity import set_workspace, get_identity
    workspace_id = body.pop("workspace_id", None)
    workspace = None
    workspace_token = None
    
    # Get user from identity context (tenant_id, user_id)
    tenant_id, user_id = get_identity()
    
    if workspace_id and user_id:
        try:
            from apps.backend.infrastructure.workspace_service import ensure_workspace
            from apps.backend.infrastructure.db import db
            
            # Create a minimal user-like object for workspace service
            class UserLike:
                def __init__(self, uid):
                    self.id = uid
                    self.role = "admin"  # Default to admin for now
            
            user_obj = UserLike(user_id)
            workspace = ensure_workspace(workspace_id, user_obj)
            logger.debug("resolved workspace: %s", workspace.get("name") if workspace else None)
        except Exception as e:
            logger.warning("failed to resolve workspace: %s", e)
    workspace_token = set_workspace(workspace)
    
    # Create user object for context
    user_obj = None
    if user_id:
        try:
            from apps.backend.infrastructure.db import db
            with db.pool().connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if row:
                        class UserObj:
                            def __init__(self, uid, role):
                                self.id = uid
                                self.role = role
                        user_obj = UserObj(user_id, row[1])
        except Exception:
            pass
    
    # Prepare context dict for tools (DDD-style, with real objects)
    tool_context = {
        "workspace": workspace,
        "user": user_obj,
    }
    
    try:

        max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
        if _raw_max_rounds is not None:
            try:
                max_tool_rounds_eff = max(1, min(int(_raw_max_rounds), config.MAX_TOOL_ROUNDS))
            except (TypeError, ValueError):
                pass

        messages = _inject_system_prompt(list(body.get("messages") or []))
        messages = _inject_dashboard_context(messages, dashboard_ctx)
        if agent_id:
            messages = _inject_agent_system_prompt(messages, agent_id)
        pf = body.get("tool_prefetch")
        if isinstance(pf, dict):
            _apply_tool_prefetch(messages, pf)
        messages = apply_user_persona_system(messages)
        messages = _inject_user_memory_context(messages, dashboard_ctx)

        model, model_reason, profile_key, model_is_override = resolve_effective_model(
            messages=messages,
            body_model=body.get("model"),
            profile_header=model_profile_header,
            override_header=model_override_header,
            bearer_user_role=bearer_user_role,
        )
        smart_route_reason = ""
        backend_override: Literal["ollama", "external"] | None = None
        if isinstance(_raw_llm_be, str):
            lo = _raw_llm_be.strip().lower()
            if lo == "ollama":
                backend_override = "ollama"
            elif lo == "external":
                backend_override = "external"
        if backend_override is None and not plain_completion and smart_llm_routing_enabled():
            # Smart routing: 0–1 extra local router call (Ollama), then one main completion — never two externals.
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
        )

        if plain_completion:
            merged_tools: list[Any] = []
            logger.debug("chat_completion: agent_plain_completion (no tools forwarded to Ollama)")
        else:
            merged_tools = _merge_tools(body.get("tools"))
        routed_category: str | None = None
        cats = classify_user_tool_categories(last_user_text(messages))
        cats = cats | extra_cats_body | extra_cats_hdr
        merged_tools = filter_merged_tools_by_categories(merged_tools, cats)
        logger.debug("tool_domain before check: %r, agent_id=%r", tool_domain, agent_id)
        if agent_id:
            agent = get_agent_registry().get_agent(agent_id)
            if agent:
                tool_domain_agent = agent.get("tool_domain")
                tool_names_agent = agent.get("tool_names", [])
                if tool_domain_agent:
                    merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain_agent)
                if tool_names_agent:
                    reg = get_registry()
                    allowed_tool_names = frozenset(tool_names_agent)
                    filtered = []
                    for spec in reg.chat_tool_specs:
                        n = spec.get("function", {}).get("name", "")
                        if n in allowed_tool_names:
                            filtered.append(spec)
                    merged_tools = filtered
                logger.info("agent %s: %d tools (domain=%s, explicit_names=%s)",
                           agent_id, len(merged_tools), tool_domain_agent, bool(tool_names_agent))
            else:
                logger.warning("agent_id %r not found in registry, falling back to tool_domain", agent_id)
        elif tool_domain:
            merged_tools = filter_merged_tools_by_domain(merged_tools, tool_domain)
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
        elif config.AGENT_ROUTER_STRICT_DEFAULT:
            routed_category = "minimal"
        else:
            routed_category = "full"

        try:
            from apps.backend.domain.identity import get_identity
            from apps.backend.domain.plugin_system.tool_policy import filter_chat_tool_specs
            from apps.backend.infrastructure.db import db as _identity_db
            from apps.backend.infrastructure.tool_operator_policy_db import policies_map

            _pmap = policies_map()
            _tenant_ctx, _user_ctx = get_identity()
            _role = _identity_db.user_role(_user_ctx)
            merged_tools = filter_chat_tool_specs(
                merged_tools,
                get_registry(),
                _pmap,
                _role,
                int(_tenant_ctx),
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

        if isinstance(_raw_tool_allow, list) and _raw_tool_allow:
            allow_set = {str(x).strip() for x in _raw_tool_allow if str(x).strip()}
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

        # Stufenweise Erkundung: tools[] immer nur Katalog — volles Schema nur via get_tool_help-Antwort.
        tools_for_request = _tools_for_chat_request(merged_tools)
        if config.AGENT_TOOLS_DENYLIST:
            deny = config.AGENT_TOOLS_DENYLIST
            tools_for_request = [
                t
                for t in tools_for_request
                if (n := _tool_spec_name(t)) is None or n not in deny
            ]

        if tools_for_request:
            names = [n for t in tools_for_request if (n := _tool_spec_name(t))]
            logger.info(
                "forwarding %d tools in chat request (llm_model_id=%s, category=%s): %s",
                len(names),
                model,
                routed_category or "full",
                names,
            )
        _log_tools_request_estimate("chat_completions", tools_for_request)
        pause_between_rounds = _coerce_body_bool(body.get("agent_pause_between_rounds"), False)
        if pause_between_rounds and control_queue is None:
            pause_between_rounds = False

        options = {
            k: v
            for k, v in body.items()
            if k not in ("messages", "model", "tools", "stream", *_BODY_KEYS_STRIP_FROM_OLLAMA)
        }

        def merge_add_tools_from_message(names: list[Any]) -> None:
            existing = {
                x for x in (_tool_spec_name(s) for s in tools_for_request) if x
            }
            for raw in names:
                nn = str(raw).strip()
                if not nn or nn in existing:
                    continue
                if nn in config.AGENT_TOOLS_DENYLIST:
                    continue
                sp = _registry_tool_spec_by_registered_name(nn)
                if not sp:
                    continue
                slim = _tools_for_chat_request([sp])
                if slim:
                    tools_for_request.append(slim[0])
                    existing.add(nn)

        def handle_control_dict(m: dict[str, Any]) -> bool:
            """Apply cancel/add_tools. Returns True if cancel was requested."""
            t = m.get("type")
            if t == "cancel" and cancel_event is not None:
                cancel_event.set()
                return True
            if t == "add_tools":
                raw_names = m.get("names")
                nlist = raw_names if isinstance(raw_names, list) else []
                merge_add_tools_from_message(nlist)
            return False

        async def drain_control_queue() -> None:
            if control_queue is None:
                return
            while True:
                try:
                    m = control_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if not isinstance(m, dict):
                    continue
                if m.get("type") == "continue_step":
                    logger.debug("discarding stray continue_step (not in agent.step_wait)")
                    continue
                handle_control_dict(m)

        async def wait_for_continue_step_after_round(completed_round: int) -> None:
            if control_queue is None:
                return
            if event_emit:
                await event_emit(
                    {
                        "type": "agent.step_wait",
                        "after_round": completed_round,
                        "next_round": completed_round + 1,
                        "max_rounds": max_tool_rounds_eff,
                        "detail": (
                            "Send a frame {\"type\":\"continue_step\"} to start the next LLM round. "
                            "You may send {\"type\":\"add_tools\",\"names\":[\"...\"]} before that."
                        ),
                    }
                )
            while True:
                m = await control_queue.get()
                if not isinstance(m, dict):
                    continue
                if m.get("type") == "continue_step":
                    await drain_control_queue()
                    if cancel_event is not None and cancel_event.is_set():
                        if event_emit:
                            await event_emit(
                                {
                                    "type": "agent.cancelled",
                                    "phase": "step_wait",
                                    "round": completed_round + 1,
                                }
                            )
                        raise AgentChatCancelled()
                    return
                if handle_control_dict(m):
                    if event_emit:
                        await event_emit(
                            {
                                "type": "agent.cancelled",
                                "phase": "step_wait",
                                "round": completed_round + 1,
                            }
                        )
                    raise AgentChatCancelled()

        forwarded_preview = [n for t in tools_for_request if (n := _tool_spec_name(t)) is not None]
        if event_emit:
            await event_emit(
                {
                    "type": "agent.session",
                    "routed_category": routed_category,
                    "router_categories": sorted(cats),
                    "forwarded_tools": forwarded_preview,
                    "effective_model": model,
                    "model_resolution": model_reason,
                    "llm_backend": llm_backend,
                    "smart_route_reason": smart_route_reason or None,
                }
            )

        for round_i in range(max_tool_rounds_eff):
            await drain_control_queue()
            if cancel_event is not None and cancel_event.is_set():
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.cancelled",
                            "phase": "before_llm",
                            "round": round_i + 1,
                        }
                    )
                raise AgentChatCancelled()

            tools_for_round = list(tools_for_request)
            allowed_names = _names_from_tool_list(tools_for_round)

            if event_emit:
                await event_emit(
                    {
                        "type": "agent.llm_round_start",
                        "round": round_i + 1,
                        "max_rounds": max_tool_rounds_eff,
                        "forwarded_tool_names": [
                            n for t in tools_for_round if (n := _tool_spec_name(t)) is not None
                        ],
                    }
                )

            payload_base: dict[str, Any] = {
                "messages": messages,
                "stream": False,
                **options,
            }
            if tools_for_round:
                payload_base["tools"] = tools_for_round

            last_failover: httpx.HTTPStatusError | None = None
            chosen: tuple[str, dict[str, str], str] | None = None
            data: dict[str, Any] = {}
            tools_omitted = False
            while True:
                last_failover = None
                for b_url, b_headers, b_model in attempts:
                    pl = dict(payload_base)
                    pl["model"] = b_model
                    try:
                        data, tools_omitted = await asyncio.to_thread(
                            ollama_post_chat_completions,
                            b_url,
                            pl,
                            headers=b_headers,
                            timeout=600.0,
                        )
                        chosen = (b_url, b_headers, b_model)
                        model = b_model
                        break
                    except httpx.HTTPStatusError as e:
                        last_failover = e
                        if llm_backend == "external" and external_llm_should_failover(
                            e.response.status_code
                        ):
                            logger.warning(
                                "LLM external attempt failed (status=%s); trying next endpoint",
                                e.response.status_code,
                            )
                            continue
                        err_body = _redact_provider_error_text_for_log(
                            e.response.text, max_len=600
                        )
                        logger.error(
                            "LLM chat/completions failed (%s): status=%s llm_model_id=%s body=%s",
                            llm_backend,
                            e.response.status_code,
                            b_model,
                            err_body,
                        )
                        raise
                else:
                    if last_failover is not None:
                        err_body = _redact_provider_error_text_for_log(
                            last_failover.response.text, max_len=600
                        )
                        if (
                            llm_backend == "external"
                            and last_failover.response.status_code == 429
                        ):
                            local_model = ollama_model_for_profile(profile_key)
                            attempts, llm_backend = llm_chat_transport(
                                local_model,
                                profile_key,
                                False,
                                backend_override="ollama",
                            )
                            model = local_model
                            logger.warning(
                                "LLM external: all endpoints returned 429 (quota/rate limit); "
                                "falling back to Ollama for this request (llm_model_id=%s). Next rounds use Ollama.",
                                local_model,
                            )
                            continue
                        logger.error(
                            "LLM external: all endpoints failed, last status=%s body=%s",
                            last_failover.response.status_code,
                            err_body,
                        )
                        raise last_failover
                    raise RuntimeError("LLM: no chat/completions attempts")
                break

            if chosen is None:
                raise RuntimeError("LLM: internal error: no completion chosen after HTTP success")

            if tools_omitted:
                tools_for_round = []
                allowed_names = set()

            choice0, msg, tool_calls, had_native_tool_calls = (
                _extract_tool_calls_from_completion_response(
                    data,
                    allowed_tool_names=allowed_names,
                )
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
                and config.AGENT_TOOL_CHOICE_REQUIRED_RETRY
            ):
                payload_retry = dict(payload_base)
                payload_retry["model"] = chosen[2]
                payload_retry["tool_choice"] = "required"
                try:
                    data_r, tools_omitted_r = await asyncio.to_thread(
                        ollama_post_chat_completions,
                        chosen[0],
                        payload_retry,
                        headers=chosen[1],
                        timeout=600.0,
                    )
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (400, 422):
                        logger.warning(
                            "Ollama rejected tool_choice=required (status=%s); keeping first completion. body~=%s",
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

            _log_ollama_round(
                round_i=round_i,
                max_rounds_cap=max_tool_rounds_eff,
                model=model,
                messages=messages,
                tools_for_round=tools_for_round,
                msg=msg,
                choice0=choice0 if isinstance(choice0, dict) else {},
                tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                had_native_tool_calls=had_native_tool_calls,
            )

            if event_emit:
                tc_names = [
                    (tc.get("function") or {}).get("name")
                    for tc in (tool_calls or [])
                    if isinstance(tc, dict)
                ]
                await event_emit(
                    {
                        "type": "agent.llm_round",
                        "round": round_i + 1,
                        "tool_calls": [str(x) for x in tc_names if x],
                        "had_native_tool_calls": had_native_tool_calls,
                        "content_excerpt": (
                            (msg.get("content") or "")[:400]
                            if isinstance(msg.get("content"), str)
                            else ""
                        ),
                    }
                )

            if not tool_calls:
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.done",
                            "kind": "final_text",
                            "round": round_i + 1,
                        }
                    )
                return data

            # Append assistant message (includes tool_calls, and content if any)
            messages.append(msg)

            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = _parse_tool_arguments(fn.get("arguments"))
                tool_call_id = tc.get("id") or ""
                logger.info("tool round %s: %s(%s)", round_i + 1, name, args)
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.tool_start",
                            "round": round_i + 1,
                            "name": name,
                        }
                    )
                tctx = set_tool_invocation_messages(list(messages))
                try:
                    result = execute_tool(name, args, context=tool_context)
                finally:
                    reset_tool_invocation_messages(tctx)
                if event_emit:
                    await event_emit(
                        {
                            "type": "agent.tool_done",
                            "round": round_i + 1,
                            "name": name,
                            "result_chars": len(result or ""),
                        }
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

            if (
                pause_between_rounds
                and control_queue is not None
                and round_i + 1 < max_tool_rounds_eff
            ):
                await wait_for_continue_step_after_round(round_i + 1)

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
                    "kind": "max_tool_rounds",
                    "round": max_tool_rounds_eff,
                }
            )
        return data
    finally:
        reset_capability_confirmed(_cap_cf_tok)
        from apps.backend.domain.identity import reset_workspace
        if workspace_token:
            reset_workspace(workspace_token)
