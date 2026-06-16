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

from apps.backend.domain.agent_io import (  # noqa: E402
    _extract_first_json_object,
    _format_normalized_tool_args_for_recap,
    _parse_named_parenthesized_tool_call,
    _parse_tool_arguments,
    _text_blobs_from_message,
)
from apps.backend.domain.agent_prompts import (  # noqa: E402
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
    from apps.backend.api.rag import embed_one

    from apps.backend.infrastructure import agent_config_effective

    if not agent_config_effective.effective_bool("tool_forward.ranking_enabled", default=config.AGENT_TOOLS_RANKING_ENABLED) or not user_input or not tools:
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
        logfn = logger.debug if config.AGENT_LOG_TOOL_PIPELINE else logger.info
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
    logfn = logger.debug if config.AGENT_LOG_TOOL_PIPELINE else logger.info
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


def _tool_error_suggests_incomplete_arguments(error: str | None) -> bool:
    """Generic: tool runtime/validation message implies more JSON fields were expected."""
    err = (error or "").strip().lower()
    if not err:
        return False
    markers = (
        " is required",
        "required for",
        "pass ",
        "missing ",
        "must be ",
        "provide ",
        "omit if unambiguous",
    )
    return any(m in err for m in markers)


def _tool_parameter_recovery_hint(tool_name: str, result: str) -> str | None:
    """Short system nudge when models emit tool_calls without required JSON fields (common on some GGUF builds)."""
    if tool_name in PLANNER_NO_EXTRA_HINTS_AFTER_TOOL:
        return None
    if not result or len(result) > 4000:
        return None
    try:
        obj = json.loads(result)
        if not isinstance(obj, dict):
            return None
        if obj.get("error") == "tool_call_arguments_invalid":
            hint = str(obj.get("hint") or "").strip()
            if obj.get("parameters"):
                schema_note = (
                    f"Full schema for `{tool_name}` is in the last tool result JSON under `parameters`. "
                    "Use those property names in the next tool_calls[].function.arguments object."
                )
                return f"{hint}\n\n{schema_note}"[:2500] if hint else schema_note[:2500]
            if hint:
                return hint[:2500]
        if obj.get("ok") is False:
            err = str(obj.get("error") or "").strip()
            if _tool_error_suggests_incomplete_arguments(err):
                return (
                    f"Tool `{tool_name}` failed: {err}\n\n"
                    "Put **all** fields the error implies into the next native `tool_calls[].function.arguments` "
                    f"JSON object (not prose). Full schema for `{tool_name}` may appear in tools[] next round."
                )[:2500]
    except json.JSONDecodeError:
        pass
    return None


def _arg_value_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _args_effectively_empty(args: dict[str, Any]) -> bool:
    if not args:
        return True
    return not any(_arg_value_present(v) for v in args.values())


def _unwrap_tool_args_aliases(args: dict[str, Any]) -> dict[str, Any]:
    """Unwrap ``{"arguments": {...}}`` / ``{"params": {...}}`` nesting from sloppy tool JSON."""
    if not isinstance(args, dict) or not args:
        return {}
    out = dict(args)
    if len(out) == 1:
        for alt in ("arguments", "args", "params", "parameters", "input", "payload", "body"):
            nested = out.get(alt)
            if isinstance(nested, dict) and nested:
                return dict(nested)
    return out


def _tool_schema_names_match(requested: str, registered: str) -> bool:
    if requested == registered:
        return True
    if requested.endswith(f".{registered}"):
        return True
    if registered.endswith(f".{requested}"):
        return True
    return False


def _infer_tool_args_from_message(tool_name: str, assistant_msg: dict[str, Any]) -> dict[str, Any]:
    """Recover JSON args from assistant prose when wire ``tool_calls[].arguments`` is ``{}``."""
    name = (tool_name or "").strip()
    if not name:
        return {}
    name_candidates = [name]
    if "." in name:
        short = name.rsplit(".", 1)[-1]
        if short and short not in name_candidates:
            name_candidates.append(short)
    for blob in _text_blobs_from_message(assistant_msg):
        text = (blob or "").strip()
        if not text:
            continue
        for candidate in name_candidates:
            parsed = _parse_named_parenthesized_tool_call(text, candidate)
            if isinstance(parsed, dict) and parsed:
                return dict(parsed)
        obj = _extract_first_json_object(text)
        if not isinstance(obj, dict):
            continue
        declared = (
            obj.get("name")
            or obj.get("tool")
            or obj.get("tool_name")
            or obj.get("function")
        )
        declared_s = str(declared or "").strip()
        if declared_s in name_candidates or any(
            _tool_schema_names_match(name, declared_s) for name in name_candidates
        ):
            for alt in ("arguments", "args", "parameters", "params", "input"):
                nested = obj.get(alt)
                if isinstance(nested, dict) and nested:
                    return dict(nested)
    return {}


def _lookup_tool_parameter_schema(tool_name: str) -> dict[str, Any] | None:
    """Exact registered tool name only — no fuzzy suffix match (``create`` ≠ ``workspace.create``)."""
    n = (tool_name or "").strip()
    if not n:
        return None
    try:
        spec = _registry_tool_spec_by_registered_name(n)
        if not spec:
            return None
        fn = spec.get("function")
        if not isinstance(fn, dict):
            return {}
        params = fn.get("parameters")
        return dict(params) if isinstance(params, dict) else {}
    except Exception:
        logger.debug("tool schema lookup failed for %r", n, exc_info=True)
    return None


def _present_schema_properties(args: dict[str, Any], schema: dict[str, Any]) -> int:
    props = schema.get("properties")
    if isinstance(props, dict) and props:
        return sum(1 for key in props if _arg_value_present(args.get(key)))
    return sum(1 for value in args.values() if _arg_value_present(value))


def _schema_branch_satisfied(branch: dict[str, Any], args: dict[str, Any]) -> bool:
    required = branch.get("required")
    if isinstance(required, list) and required:
        return all(_arg_value_present(args.get(str(key))) for key in required)
    min_props = branch.get("minProperties")
    if isinstance(min_props, int) and min_props > 0:
        return _present_schema_properties(args, branch) >= min_props
    return False


def _tool_args_validation_hint(
    tool_name: str,
    schema: dict[str, Any] | None,
    *,
    missing: list[str],
    any_of_fields: list[str] | None,
) -> str:
    props = (schema or {}).get("properties") if isinstance(schema, dict) else None
    if any_of_fields:
        fields = " or ".join(f"**{k}**" for k in any_of_fields)
        return (
            f"Tool `{tool_name}` requires a non-empty JSON argument object with at least one of: {fields}. "
            "Do not emit wire-format `tool_calls` with `{}` — pass the schema fields in `arguments`."
        )
    if missing and isinstance(props, dict):
        parts = []
        for key in missing[:6]:
            desc = props.get(key, {})
            hint = ""
            if isinstance(desc, dict):
                hint = str(desc.get("TOOL_DESCRIPTION") or desc.get("description") or "").strip()
            parts.append(f"**{key}**" + (f" ({hint})" if hint else ""))
        return (
            f"Tool `{tool_name}` was called with empty or incomplete arguments. "
            f"Required: {', '.join(parts)}. "
            "Fix the next `tool_calls[].function.arguments` JSON — do not call the tool with `{}`."
        )
    return (
        f"Tool `{tool_name}` was called with empty or incomplete arguments. "
        "Provide non-empty JSON per the tool schema. "
        "The tool result includes `parameters` with the full JSON Schema for the next call."
    )


def validate_tool_call_arguments(tool_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
    """
    Return an error payload when args are too empty to execute; ``None`` when OK.

    Uses each tool's registered JSON Schema only (``required``, ``minProperties``, ``anyOf``).
    """
    n = (tool_name or "").strip()
    if not n:
        return {
            "ok": False,
            "error": "tool_call_arguments_invalid",
            "tool": n,
            "message": "missing tool name on tool_call",
        }

    schema = _lookup_tool_parameter_schema(n) or {}
    missing: list[str] = []
    for req in schema.get("required") or []:
        key = str(req)
        if not _arg_value_present(args.get(key)):
            missing.append(key)

    any_of_fields: list[str] = []
    any_of = schema.get("anyOf")
    if isinstance(any_of, list) and any_of:
        if not any(isinstance(branch, dict) and _schema_branch_satisfied(branch, args) for branch in any_of):
            for branch in any_of:
                if not isinstance(branch, dict):
                    continue
                for req in branch.get("required") or []:
                    field = str(req)
                    if field not in any_of_fields:
                        any_of_fields.append(field)
            if not missing:
                missing = any_of_fields

    min_props = schema.get("minProperties")
    if isinstance(min_props, int) and min_props > 0:
        if _present_schema_properties(args, schema) < min_props and not missing:
            props = schema.get("properties")
            if isinstance(props, dict):
                missing = list(props.keys())[:6]
            else:
                missing = ["(at least one property required)"]

    if missing:
        payload: dict[str, Any] = {
            "ok": False,
            "error": "tool_call_arguments_invalid",
            "tool": n,
            "message": f"Tool {n!r} rejected: empty or incomplete arguments.",
            "missing_or_empty": missing,
            "schema_required": list(schema.get("required") or []),
            "any_of_required": any_of_fields,
            "received_arguments": dict(args),
            "hint": _tool_args_validation_hint(
                n, schema, missing=missing, any_of_fields=any_of_fields or None
            ),
        }
        if schema:
            payload["parameters"] = copy.deepcopy(schema)
        return payload
    return None


def format_tool_call_validation_error(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def tool_call_warrants_full_schema_promotion(
    *,
    rejected: bool,
    wire_args: dict[str, Any],
    normalized_args: dict[str, Any],
    result_ok: bool | None,
    result_error: str | None = None,
) -> bool:
    """Promote a tool to full schema on the next LLM round (reject, empty wire, or incomplete-args failure)."""
    _ = normalized_args
    if rejected:
        return True
    if result_ok is True:
        return False
    if result_ok is False and _tool_error_suggests_incomplete_arguments(result_error):
        return True
    if _args_effectively_empty(wire_args):
        return True
    return False


def _normalize_tool_call_arguments(
    name: str,
    args: dict[str, Any],
    assistant_msg: dict[str, Any],
    messages: list[dict[str, Any]],
    tool_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unwrap aliased tool JSON nesting only — wire arguments are never inferred from prose."""
    _ = (name, assistant_msg, messages, tool_context)
    return _unwrap_tool_args_aliases(dict(args))


def _agent_tool_budget_system_message(max_rounds: int) -> str:
    """Injected once per agent tool-loop request so models know the exact server cap."""
    n = max(1, int(max_rounds))
    if n <= 1:
        return (
            "## Tool-loop budget (server)\n\n"
            "This reply allows **only one** tool-loop LLM round (one completion; optional tool_calls). "
            "Use tools only if needed, then answer — the user can continue in a **new message** if more rounds are required."
        )
    return (
        "## Tool-loop budget (server)\n\n"
        f"- The server allows **at most {n}** tool-loop LLM rounds for this assistant reply (counting this completion).\n"
        "- **This is round 1** — `tools[]` is available; use `tool_calls` when needed to answer the **latest user message**.\n"
        "- Avoid empty `{}` tool JSON (often normalizes to identical calls and can trigger loop guards).\n\n"
        "If work is unfinished, say so explicitly — the user may send a follow-up message."
    )


def _agent_near_max_tool_rounds_reminder(current_round: int, max_rounds: int) -> str:
    """Shown the round before the final text-only round (requires max_rounds >= 3)."""
    return (
        f"You are in **LLM tool-loop round {current_round} of {max_rounds}**. "
        f"The **next** round ({current_round + 1}) is the **last**; it will be **text-only** (no tools in the API). "
        "Finish critical tool calls **this** round if you still need them, or prepare a complete plain-text "
        "wrap-up on the next turn."
    )


def _agent_final_round_text_only_hint(current_round: int, max_rounds: int) -> str:
    """Shown immediately before the final LLM call (no tools[])."""
    return (
        f"**Round {current_round} of {max_rounds}** — final tool-loop round: **no** `tools[]` will be sent. "
        "Reply with **plain Markdown only** — the API **never** runs tools from prose. "
        "**Never** write `<tool_call>`, `</tool_call>`, `<function=…>`, or similar XML.\n\n"
        "**You must do exactly one of:**\n"
        "(A) **Synthesize** everything useful from **existing** `tool` messages above (findings, errors, paths, "
        "open questions, next steps for the user); **or**\n"
        "(B) If the transcript is **not** enough to answer, say that plainly and tell the user to send **one new "
        "message** to continue (a new request gets a fresh tool budget — you cannot call more tools in this reply).\n\n"
        "Do not stall with vague intent to explore — either recap what you already have, or ask for a follow-up."
    )


def _rewrite_delegatable_agent_tool_alias(
    name: str,
    args: dict[str, Any],
    *,
    allowed_names: set[str] | frozenset[str],
    messages: list[dict[str, Any]],
    caller_is_admin: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    """Map ``agent_id`` used as tool name (e.g. ``math``) to ``delegate`` when allowed."""
    n = (name or "").strip()
    if not n or n in allowed_names or "delegate" not in allowed_names:
        return None
    from apps.backend.domain.embedded_subagent import effective_delegatable_agent_ids

    if n not in effective_delegatable_agent_ids(caller_is_admin=caller_is_admin):
        return None
    prompt = ""
    for key in ("prompt", "expression", "query", "task", "message"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            prompt = val.strip()
            break
    if not prompt:
        prompt = (last_user_text(messages) or "").strip()
    if not prompt:
        return None
    return (
        "delegate",
        {
            "agent_id": n,
            "prompt": prompt,
            "run_subagent": True,
        },
    )


def _agent_session_tool_recap_system_message(
    batch_parts: list[str],
    *,
    overflow_tail: str = "",
    user_task: str = "",
) -> str:
    """Post-tool status plus explicit user task so small models do not lose the request."""
    status = ", ".join(batch_parts) + overflow_tail
    ut = (user_task or "").strip()
    task_section = ""
    if ut:
        if len(ut) > 6000:
            ut = ut[:6000] + "\n…[truncated]"
        task_section = (
            "## User request (complete this now)\n\n"
            f"{ut}\n\n"
        )
    return (
        task_section
        + "## Server tool batch status (internal — not a user message)\n\n"
        f"Tools just executed in this reply: **{status}**.\n\n"
        "Answer the **user request** section above using the **`tool` role payloads** in the transcript. "
        "Call more tools if the task is incomplete; otherwise reply with the facts the user asked for."
    )


def _assistant_plain_text_from_message(msg: dict[str, Any]) -> str:
    return "\n".join(_text_blobs_from_message(msg)).strip()


_TOOL_RECAP_HEADER = "## Tool transcript (server-extracted)"
_ROUNDS_DIGEST_HEADER = "## LLM tool rounds (server-extracted)"


def _tool_call_id_to_name_map(messages: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") or {}
            nm = str(fn.get("name") or "").strip() if isinstance(fn, dict) else ""
            if tid and nm:
                out[tid] = nm
    return out


def _tool_call_id_to_args_recap_line(messages: list[dict[str, Any]], *, max_len: int = 400) -> dict[str, str]:
    """Short, human-readable args from prior assistant ``tool_calls`` (by ``tool_call_id``).

    Uses the same :func:`_normalize_tool_call_arguments` as execution so defaults (e.g.
    ``list_dir`` → ``path=.``) show up, and empty ``glob`` shows
    ``pattern=<missing>``.
    """
    out: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tid = str(tc.get("id") or "").strip()
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict) or not tid:
                continue
            name = str(fn.get("name") or "").strip()
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            out[tid] = _format_normalized_tool_args_for_recap(name, norm, max_len=max_len)
    return out


def _summarize_tool_json_body(raw: str, *, max_body: int) -> str:
    s = (raw or "").strip()
    if not s:
        return "(empty)"
    if not s.startswith("{"):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if not isinstance(o, dict):
        return s[:max_body] + ("…" if len(s) > max_body else "")

    meta: list[str] = []
    if "ok" in o:
        meta.append(f"ok={bool(o.get('ok'))}")
    for key in ("path", "pattern", "query", "path_prefix", "operation", "search_engine"):
        val = o.get(key)
        if isinstance(val, str) and val.strip():
            u = val.strip().replace("\n", " ")
            if len(u) > 220:
                u = u[:220] + "…"
            meta.append(f"{key}={u}")
    if "regex" in o and isinstance(o.get("regex"), bool):
        meta.append(f"regex={bool(o.get('regex'))}")
    ec = o.get("exit_code")
    if isinstance(ec, int) or (isinstance(ec, str) and str(ec).strip().isdigit()):
        meta.append(f"exit_code={ec}")
    if isinstance(o.get("count"), int):
        meta.append(f"count={o['count']}")
    if isinstance(o.get("files_scanned"), int):
        meta.append(f"files_scanned={o['files_scanned']}")
    if isinstance(o.get("line_count_total"), int):
        meta.append(f"line_count_total={o['line_count_total']}")
    if o.get("truncated") is True or o.get("truncated_lines") is True:
        meta.append("truncated=true")
    if o.get("truncated_matches") is True:
        meta.append("truncated_matches=true")
    if o.get("truncated_scan") is True:
        meta.append("truncated_scan=true")
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        meta.append("error=" + err.strip()[:480])
    th = o.get("truncation_hint")
    if isinstance(th, str) and th.strip():
        u = th.strip().replace("\n", " ")
        meta.append("hint=" + (u[:300] + "…" if len(u) > 300 else u))
    if o.get("deduplicated") is True:
        meta.append("deduplicated=true")
    srv_note = o.get("message")
    u = (srv_note if isinstance(srv_note, str) else "").strip()
    dedup = o.get("deduplicated") is True
    if dedup:
        # Avoid repeating the same long boilerplate for every skipped parallel/loop call.
        if u.startswith("Identical tool+arguments"):
            previews_note = (
                "server_note: _(skipped — identical tool+args; use the earlier matching result "
                "in this transcript)_"
            )
        elif u:
            previews_note = "server_note:\n" + (u if len(u) <= 400 else u[:400] + "…")
        else:
            previews_note = "server_note: _(skipped — identical tool+args)_"
    elif u:
        previews_note = "server_note:\n" + (u if len(u) <= 900 else u[:900] + "…")
    else:
        previews_note = ""

    previews: list[str] = []
    if previews_note:
        previews.append(previews_note)

    files = o.get("files")
    if isinstance(files, list) and files:
        names = [str(x).replace("\n", " ") for x in files[:45] if x is not None]
        if names:
            tail = len(files) - len(names)
            head = ", ".join(names)
            if tail > 0:
                head += f" …(+{tail} more in payload)"
            previews.append(f"files ({len(files)}): {head}")

    entries = o.get("entries")
    if isinstance(entries, list) and entries:
        bits: list[str] = []
        for ent in entries[:35]:
            if not isinstance(ent, dict):
                continue
            p = str(ent.get("path") or ent.get("name") or "").strip()
            if not p:
                continue
            suf = "/" if ent.get("is_dir") else ""
            bits.append(p + suf)
        if bits:
            tail = len(entries) - len(bits)
            line = ", ".join(bits)
            if tail > 0:
                line += f" …(+{tail} more entries)"
            previews.append(f"listing: {line}")

    matches = o.get("matches")
    if isinstance(matches, list) and matches:
        mlines: list[str] = []
        for m in matches[:14]:
            if not isinstance(m, dict):
                continue
            pth = str(m.get("path") or "").strip()
            ln = m.get("line")
            tx = m.get("text")
            ts = tx.strip()[:180] + ("…" if isinstance(tx, str) and len(tx.strip()) > 180 else "") if isinstance(tx, str) else ""
            if pth and isinstance(ln, int):
                mlines.append(f"  {pth}:{ln}: {ts}".rstrip())
            elif pth:
                mlines.append(f"  {pth}: {ts}".rstrip())
        if mlines:
            tail = len(matches) - len(mlines)
            block = "matches:\n" + "\n".join(mlines)
            if tail > 0:
                block += f"\n  …(+{tail} more matches)"
            previews.append(block)

    out_text = o.get("output")
    if isinstance(out_text, str) and out_text.strip():
        u = out_text.strip()
        previews.append("output:\n" + (u if len(u) <= max_body - 80 else u[: max_body - 80] + "…"))

    content = o.get("content")
    if isinstance(content, str) and content.strip() and "path" in o:
        u = content.strip()
        cap = min(1600, max(200, max_body - 120))
        previews.append(
            "file_content:\n"
            + (u if len(u) <= cap else u[:cap] + "…")
        )

    body = " | ".join(meta) if meta else ""
    for p in previews:
        if not p.strip():
            continue
        sep = "\n" if body else ""
        if len(body) + len(sep) + len(p) > max_body:
            room = max_body - len(body) - len(sep) - 1
            if room > 40:
                body += sep + p[:room] + "…"
            else:
                body += "\n…[preview truncated]"
            break
        body += sep + p

    if not body.strip():
        return s[:max_body] + ("…" if len(s) > max_body else "")
    if len(body) > max_body:
        return body[:max_body] + "…"
    return body


def _build_tool_transcript_recap(
    messages: list[dict[str, Any]],
    *,
    max_entries: int = 32,
    max_body_chars: int = 2200,
) -> str:
    """Deterministic markdown from ``role: tool`` payloads (JSON-aware)."""
    id_to_name = _tool_call_id_to_name_map(messages)
    id_to_args = _tool_call_id_to_args_recap_line(messages, max_len=400)
    lines: list[str] = []
    n = 0
    for m in messages:
        if m.get("role") != "tool":
            continue
        n += 1
        if n > max_entries:
            lines.append(f"\n_…{n - max_entries} more tool message(s) omitted._\n")
            break
        tid = str(m.get("tool_call_id") or "").strip()
        name = id_to_name.get(tid, "tool")
        body = m.get("content")
        text = body if isinstance(body, str) else str(body)
        summ = _summarize_tool_json_body(text, max_body=max_body_chars)
        req = (id_to_args.get(tid) or "").strip()
        if req:
            req_safe = req.replace("`", "'")
            lines.append(f"### {n}. `{name}`\n**Tool args:** `{req_safe}`\n{summ}\n")
        else:
            lines.append(f"### {n}. `{name}`\n{summ}\n")
    if not lines:
        return f"{_TOOL_RECAP_HEADER}\n\n_No tool messages in this reply._\n"
    return f"{_TOOL_RECAP_HEADER}\n\n" + "\n".join(lines)


def _build_llm_tool_rounds_digest(
    messages: list[dict[str, Any]],
    *,
    max_rounds_shown: int = 32,
    max_calls_per_round: int = 24,
    max_args_len: int = 320,
) -> str:
    """Per-assistant-turn list of tool names + normalized args (what the model *requested*)."""
    blocks: list[str] = []
    r = 0
    for m in messages:
        if m.get("role") != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list) or not tcs:
            continue
        r += 1
        if r > max_rounds_shown:
            blocks.append(f"_…{r - max_rounds_shown} more LLM tool round(s) omitted._")
            break
        lines: list[str] = [f"### Round {r}"]
        n_call = 0
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            n_call += 1
            if n_call > max_calls_per_round:
                rest = len(tcs) - max_calls_per_round
                lines.append(f"- _…{rest} more tool_call(s) in this round._")
                break
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("name") or "").strip() or "tool"
            raw = fn.get("arguments")
            if raw in (None, "", "{}") or (isinstance(raw, dict) and not raw):
                if isinstance(tc.get("arguments"), (str, dict)) and tc.get("arguments") not in (None, ""):
                    raw = tc.get("arguments")
            args0 = _parse_tool_arguments(raw)
            norm = _normalize_tool_call_arguments(name, dict(args0), m, messages, None)
            arg_line = _format_normalized_tool_args_for_recap(name, norm, max_len=max_args_len)
            lines.append(f"- `{name}`: {arg_line}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    return f"{_ROUNDS_DIGEST_HEADER}\n\n" + "\n\n".join(blocks)


def _build_client_tool_context_markdown(messages: list[dict[str, Any]]) -> str:
    """LLM tool rounds (requests) plus tool transcript (results) for the client-facing reply."""
    digest = _build_llm_tool_rounds_digest(messages).strip()
    recap = _build_tool_transcript_recap(messages).strip()
    if digest and recap:
        return digest + "\n\n" + recap
    return digest or recap


def _client_reply_is_only_server_tool_context_prefix(tail: str) -> bool:
    t = (tail or "").strip()
    if not t:
        return True
    return t.startswith(_TOOL_RECAP_HEADER) or t.startswith(_ROUNDS_DIGEST_HEADER)


def _merge_deterministic_tool_recap_into_final_completion(
    data: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    plain_completion: bool,
) -> bool:
    """Prefix assistant content with server recap when the tool loop ends (mutates ``data``)."""
    if plain_completion:
        return False
    try:
        recap = _build_client_tool_context_markdown(messages)
        if not recap.strip():
            return False
        cap = 18_000
        recap_use = recap if len(recap) <= cap else recap[:cap] + "\n\n…[truncated]"
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg0 = ch0.get("message")
        if not isinstance(msg0, dict):
            return False
        ex = msg0.get("content")
        if ex is None:
            msg0["content"] = ""
            ex = ""
        elif not isinstance(ex, str):
            return False
        tail = ex.strip()
        sep = "\n\n---\n\n### Model reply\n\n"
        if not tail or _client_reply_is_only_server_tool_context_prefix(tail):
            msg0["content"] = recap_use.strip()[:80_000]
        else:
            merged = (recap_use.rstrip() + sep + tail).strip()
            if len(merged) > 80_000:
                merged = merged[:80_000] + "…"
            msg0["content"] = merged
        msg0.pop("tool_calls", None)
        ch0["message"] = msg0
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


def _agent_final_text_looks_like_placeholder_tool_markup(text: str) -> bool:
    """GGUF models often emit fake XML tool blocks when tools[] is omitted."""
    if not (text or "").strip():
        return True
    tl = text.lower()
    if "<tool_call" in tl or "</tool_call>" in tl:
        return True
    if "<function=" in tl or "</function>" in tl:
        return True
    if "<invoke" in tl or "</invoke>" in tl:
        return True
    if "<tool_code" in tl or "</tool_code>" in tl:
        return True
    if "<thinking" in tl or "</thinking>" in tl:
        return True
    if re.search(r"</?(?:read_file|bash|glob|list_dir|search)\b", tl):
        return True
    if re.search(r"<parameters?\b", tl):
        return True
    if re.search(r"call:default_api:", tl):
        return True
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "command" in obj and len(obj) <= 3:
            return True
    return False


def _strip_prose_fake_tool_markup(text: str) -> str:
    """Remove non-executable tool-like XML some models print when no tools[] are sent."""
    if not text:
        return text
    out = text
    for tag in (
        r"tool_call",
        r"invoke",
        r"tool_code",
        r"thinking",
        r"read_file",
        r"bash",
        r"glob",
        r"list_dir",
        r"search",
        r"parameters?",
    ):
        out = re.sub(
            rf"<{tag}\b[^>]*>[\s\S]*?</{tag}>",
            "",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(rf"</?{tag}\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<tool_call\b[^>]*>[\s\S]*?</tool_call>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</?tool_call\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function\s*=[^>]*>\s*</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"<function[^>]*>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"</function>", "", out, flags=re.IGNORECASE)
    out = re.sub(r"```(?:json)?\s*\{[\s\S]*?\}\s*```", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _sanitize_final_completion_assistant_content(data: dict[str, Any]) -> bool:
    """Strip fake tool XML from ``choices[0].message.content`` when present (mutates ``data``)."""
    try:
        ch_list = data.get("choices")
        if not isinstance(ch_list, list) or not ch_list:
            return False
        ch0 = ch_list[0]
        if not isinstance(ch0, dict):
            return False
        msg = ch0.get("message")
        if not isinstance(msg, dict):
            return False
        raw = msg.get("content")
        if not isinstance(raw, str) or not raw.strip():
            return False
        if not _agent_final_text_looks_like_placeholder_tool_markup(raw):
            return False
        stripped = _strip_prose_fake_tool_markup(raw)
        if stripped.strip():
            msg["content"] = stripped
        else:
            msg["content"] = (
                "_(The model returned tool-call markup instead of plain text — no readable answer was produced. "
                "Send a follow-up message to continue; tool results from earlier rounds are still in the transcript.)_"
            )
        msg.pop("tool_calls", None)
        ch0["message"] = msg
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False


def _synthetic_final_llm_http_error_completion(*, status: int, model_id: str) -> dict[str, Any]:
    """Minimal OpenAI-shaped completion when the last LLM call fails (proxy 502, etc.)."""
    mid = model_id if isinstance(model_id, str) and model_id.strip() else "unknown"
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": (
                        f"_(The language model server returned **HTTP {status}** on the **final summary** round "
                        f"(model `{mid}`) — no generated answer was returned.)_\n\n"
                        "**What you can do:** wait a moment and **retry**; check **Agent activity** for outputs from "
                        "earlier tool rounds in this reply; send a **new message** asking to summarize those results "
                        "or to keep exploring (that starts a fresh tool budget)._"
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "model": mid,
    }


_AGENT_TOOL_THRASH_HINT = (
    "Tool loop guard: the same tool has failed **repeatedly** with the **same error message**. "
    "On the next assistant message you must either fix the JSON arguments (non-empty fields per schema) "
    "or answer the user in **plain text** explaining what is wrong — do not repeat identical failing tool calls."
)


_AGENT_TOOL_THRASH_FORCE_TEXT = (
    "Repeated identical tool failures were detected. **Tools are disabled for this round** — respond with a "
    "normal assistant message only: summarize the error, quote it briefly, and state the exact JSON fields "
    "required for the next successful call (e.g. coding_bash → `{\"command\": \"…\"}`)."
)

_AGENT_TOOL_DOOM_LOOP_HINT = (
    "Loop guard: the **same tool** was called with the **same arguments** repeatedly. "
    "Stop repeating that call: change parameters, try a different approach, or answer the user in **plain text** "
    "with what you learned and what to do next. "
    "If this is **read-only Plan** mode, synthesize your **handoff plan** now (markdown): proposed edits, files for Build, "
    "checklist — do not call that tool again with the same args."
)

_AGENT_TOOL_DOOM_FORCE_TEXT = (
    "Repeated identical tool calls were detected. **Tools are disabled for this assistant turn** — reply with a "
    "normal message only: summarize what tool output you already have, then deliver a **complete plan** "
    "(markdown): proposed changes, files/paths for the Build agent, ordered steps. "
    "Ask at most one clarifying question if something essential is still unknown. "
    "Do **not** emit fake `<tool_call>` / `</tool_call>` or XML tool markup — the chat API does not parse that from text."
)


def _agent_tool_doom_loop_tick(
    doom_key: str | None,
    doom_count: int,
    *,
    tool_name: str,
    args: dict[str, Any],
    max_streak: int,
    exclude_names: frozenset[str],
) -> tuple[str | None, int, str | None]:
    """Detect repeated identical tool invocations (stuck doom-loop guard)."""
    if max_streak < 2:
        return doom_key, doom_count, None
    if tool_name in exclude_names:
        return doom_key, doom_count, None
    try:
        args_canon = json.dumps(dict(args), sort_keys=True, separators=(",", ":"), default=str)
    except TypeError:
        args_canon = str(args)
    if len(args_canon) > 1200:
        args_canon = args_canon[:1200] + "…"
    dk = f"{tool_name}|{args_canon}"
    if dk == doom_key:
        n = doom_count + 1
    else:
        dk, n = dk, 1
    if n >= max_streak:
        return None, 0, _AGENT_TOOL_DOOM_LOOP_HINT
    return dk, n, None


def _tool_result_summary(result: str | None) -> tuple[bool | None, str | None]:
    """Parse leading JSON object from a tool result string: (ok, error text) or (None, None) if unknown."""
    if not result or not str(result).strip():
        return None, None
    s = result.strip()
    if not s.startswith("{"):
        return None, None
    try:
        o = json.loads(s)
    except json.JSONDecodeError:
        return None, None
    if not isinstance(o, dict):
        return None, None
    if "ok" not in o:
        return None, None
    if o.get("ok") is True:
        return True, None
    err = o.get("error")
    if isinstance(err, str) and err.strip():
        return False, err.strip()
    return False, None


def _tool_result_followup_hint(tool_name: str, result: str | None) -> str | None:
    """System hint when a tool result needs explicit operator follow-up (sub-agent issues, register-only tasks)."""
    if not result or not str(result).strip().startswith("{"):
        return None
    try:
        o = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not isinstance(o, dict):
        return None
    if tool_name == "task" and o.get("mode") == "register_only":
        warn = o.get("warning") or o.get("detail")
        if isinstance(warn, str) and warn.strip():
            return (
                "coding_task did **not** run a sub-agent — it only registered a task id. "
                f"{warn.strip()} Use **agent_delegate** with run_subagent=true for real execution."
            )
    problems = o.get("problems")
    prob_lines: list[str] = []
    if isinstance(problems, list):
        prob_lines = [str(p).strip() for p in problems if isinstance(p, str) and str(p).strip()]
    if o.get("ok") is False:
        err = o.get("error")
        if isinstance(err, str) and err.strip():
            prob_lines.insert(0, err.strip())
        hint = o.get("hint")
        if isinstance(hint, str) and hint.strip():
            prob_lines.append(hint.strip())
        if prob_lines:
            who = tool_name or "tool"
            return f"{who} failed: " + " | ".join(prob_lines[:5])
    if prob_lines and tool_name in ("delegate", "task"):
        return f"{tool_name} completed with warnings: " + " | ".join(prob_lines[:5])
    if tool_name == "delegate" and o.get("ok") is True:
        excerpt = o.get("assistant_excerpt")
        if isinstance(excerpt, str) and excerpt.strip():
            from apps.backend.domain.delegate_enforcement import delegate_excerpt_is_actionable

            body = excerpt.strip()[:2000]
            if delegate_excerpt_is_actionable(excerpt):
                return (
                    "delegate succeeded. Reply to the user using the specialist result below "
                    "(summarize assistant_excerpt in natural language). "
                    "Do not call delegate again for the same task.\n\n"
                    f"assistant_excerpt:\n{body}"
                )
            return (
                "delegate returned ok but assistant_excerpt is not a usable answer "
                "(tool markup or instructions only). Retry delegate with a clearer prompt, "
                "or answer from tool results already in the sub-agent trace.\n\n"
                f"assistant_excerpt:\n{body}"
            )
    return None


async def _emit_secret_prompt_from_tool_result(
    tool_name: str,
    result: str | None,
    *,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
) -> None:
    """After ``request_user_secret``, push ``agent.secret_prompt`` to the WebSocket client."""
    if tool_name != "request_user_secret" or event_emit is None:
        return
    if not result or not str(result).strip().startswith("{"):
        return
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict) or data.get("ok") is not True:
        return
    sp = data.get("secret_prompt")
    if not isinstance(sp, dict) or not sp.get("prompt_id"):
        return
    ev: dict[str, Any] = {
        "type": "agent.secret_prompt",
        "agent_run_id": agent_run_id,
        "prompt_id": str(sp["prompt_id"]),
        "service_key": str(sp.get("service_key") or ""),
        "mode": str(sp.get("mode") or "authenticated"),
        "title": sp.get("title"),
        "help": sp.get("help"),
        "fields": sp.get("fields") if isinstance(sp.get("fields"), list) else [],
        "reason": sp.get("reason"),
    }
    await event_emit(ev)


def _agent_tool_thrash_tick(
    thrash_key: str | None,
    thrash_count: int,
    *,
    tool_name: str,
    ok_r: bool | None,
    err_r: str | None,
    max_streak: int,
) -> tuple[str | None, int, str | None, bool]:
    """
    Advance thrash detector after one tool result.

    Returns ``(new_key, new_count, optional_system_hint, force_text_only_next_round)``.
    """
    if max_streak < 2:
        return thrash_key, thrash_count, None, False
    if ok_r is True:
        return None, 0, None, False
    if ok_r is None:
        return thrash_key, thrash_count, None, False
    err_norm = (err_r or "(no error text)")[:200]
    key = f"{tool_name}|{err_norm}"
    if key == thrash_key:
        n = thrash_count + 1
    else:
        n = 1
    if n >= max_streak:
        logger.warning(
            "agent tool thrash: streak=%d tool=%s — forcing text-only next round",
            n,
            tool_name,
        )
        return None, 0, None, True
    if n == max_streak - 1:
        return key, n, _AGENT_TOOL_THRASH_HINT, False
    return key, n, None, False


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

# Tool results passed to the LLM as-is — no extra system hints appended after these calls.
PLANNER_NO_EXTRA_HINTS_AFTER_TOOL = frozenset(
    {
        "settings_patch",
        "settings_get",
        "get_tool_help",
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
