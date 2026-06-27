"""Prompt parsing, catalog, body coercion helpers."""
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
from apps.backend.application.agent_runtime.dependencies import (
    apply_repetition_guard_to_completion,
    build_retrieval_bootstrap_snippet,
    build_user_secrets_bootstrap_snippet,
    build_workspace_bound_snippet,
    dashboard_db,
    external_llm_should_failover,
    find_block_in_layout,
    http_post_chat_completions,
    llm_chat_transport,
    memory_api,
    normalize_model_catalog_owned_by,
    onboarding_for_dashboard,
    smart_llm_routing_enabled,
    stream_chat_completions_aggregate,
)
from apps.backend.domain.identity import get_identity
from apps.backend.domain.agent_registry import get_agent_registry
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

logger = logging.getLogger(__name__)

# Late import: dashboard helpers live in agent_tools (avoid circular import at load).
def _dashboard_data_agent_instructions(data: Any) -> str:
    from apps.backend.domain.agent_tools import _dashboard_data_agent_instructions as _fn

    return _fn(data)


class AgentChatCancelled(Exception):
    """Client aborted in-flight chat (e.g. WebSocket ``{"type":"cancel"}``)."""


class WorkspaceAccessDenied(Exception):
    """Raised when a named workspace cannot be bound for the current user (fail closed)."""


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


def _permission_reply_user_message(m: dict[str, Any]) -> str | None:
    raw = m.get("message")
    if isinstance(raw, str):
        t = raw.strip()
        return t[:800] if t else None
    return None


async def _wait_for_tool_permission_reply(
    *,
    control_queue: asyncio.Queue,
    cancel_event: asyncio.Event | None,
    event_emit: Callable[[dict[str, Any]], Awaitable[None]] | None,
    agent_run_id: str,
    request_id: str,
    tool_name: str,
    args_preview: str,
    round_i: int,
    handle_control: Callable[[dict[str, Any]], bool],
) -> tuple[str, str | None]:
    """Block until client sends ``permission_reply`` for ``request_id``.

    Returns ``(reply, optional_message)`` where ``reply`` is ``once``, ``always``, or ``reject``.
    """
    if event_emit:
        await event_emit(
            {
                "type": "agent.permission_ask",
                "agent_run_id": agent_run_id,
                "request_id": request_id,
                "tool_name": tool_name,
                "args_preview": args_preview,
                "round": round_i + 1,
            }
        )
    while True:
        m = await control_queue.get()
        if not isinstance(m, dict):
            continue
        if m.get("type") == "permission_reply":
            if str(m.get("request_id") or "") != request_id:
                logger.debug("discarding permission_reply (stale request_id)")
                continue
            raw = str(m.get("reply") or "").strip().lower()
            fb = _permission_reply_user_message(m)
            if raw in ("once", "allow", "1", "yes", "ok"):
                return "once", fb
            if raw in ("always", "all"):
                return "always", fb
            if raw in ("reject", "deny", "no", "0"):
                return "reject", fb
            logger.debug("invalid permission_reply reply=%r; still waiting", raw)
            continue
        if handle_control(m):
            raise AgentChatCancelled()
        if cancel_event is not None and cancel_event.is_set():
            raise AgentChatCancelled()


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


_AGENTS_AUTO_WORKSPACE_FROM_GIT_URL = frozenset({"coding", "general"})


def _agent_behavior_flags(agent_id: str | None) -> dict[str, Any]:
    """Resolved from the agent plugin registry — no hard-coded agent id lists for these flags."""
    base: dict[str, Any] = {
        "strict_workspace": False,
        "coding_tools_permission_ask": False,
        "tool_discipline_preset": None,
    }
    if not agent_id or not str(agent_id).strip():
        return base
    ag = get_agent_registry().get_agent(str(agent_id).strip())
    if not ag:
        return base
    preset = ag.get("tool_discipline_preset")
    preset_norm: str | None = None
    if isinstance(preset, str) and preset.strip():
        preset_norm = preset.strip().lower()
    return {
        "strict_workspace": bool(ag.get("strict_workspace")),
        "coding_tools_permission_ask": bool(ag.get("coding_tools_permission_ask")),
        "tool_discipline_preset": preset_norm,
    }


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
            f"Use this dashboard_id for all dashboard tools (read, list_append, patch_data, patch_layout, …). "
            f"If unsure which board, call dashboard.list first."
        )
        extra = _dashboard_data_agent_instructions(ws.get("data"))
        if extra:
            note = note + "\n\n[Dashboard-specific agent instructions]\n" + extra
        try:
            ob = onboarding_for_dashboard(ws, "de")
            if ob is None:
                ob = onboarding_for_dashboard(ws, "en")
            if ob:
                ap = (ob.get("agent_prompt") or "").strip()
                if ap:
                    note = note + "\n\n[Dashboard onboarding — follow when user sets up or board is new]\n" + ap
                steps = ob.get("steps") or []
                if steps:
                    labels = [str(s.get("label") or s.get("id") or "") for s in steps if isinstance(s, dict)]
                    labels = [x for x in labels if x]
                    if labels:
                        note = note + "\nSetup steps to offer: " + "; ".join(labels)
        except Exception:
            pass
        block_raw = raw.get("block_id")
        if isinstance(block_raw, str) and block_raw.strip():
            try:
                blk = find_block_in_layout(
                    ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {},
                    block_raw.strip(),
                )
            except Exception:
                blk = None
            if blk:
                btype = str(blk.get("type") or "").strip()
                props = blk.get("props") if isinstance(blk.get("props"), dict) else {}
                btitle = str(props.get("title") or "").strip()
                data_path = str(props.get("dataPath") or props.get("data_path") or "").strip()
                note = (
                    note
                    + f"\n\n[Focused dashboard block] The user pinned block_id={block_raw.strip()!r} "
                    f"for this chat turn. type={btype!r}"
                    + (f", title={btitle!r}" if btitle else "")
                    + (f", dataPath={data_path!r}" if data_path else "")
                    + ". When they ask to change 'this block', 'diesen Block', or similar, use "
                    "dashboard.patch_layout with set_props/set_grid on this block_id (and dashboard.read first if needed). "
                    "Do not redesign the whole board unless they ask for a full layout proposal."
                )
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


def _inject_user_secrets_bootstrap(
    messages: list[dict[str, Any]], user_id: Any
) -> list[dict[str, Any]]:
    if user_id is None:
        return messages
    try:
        snippet = build_user_secrets_bootstrap_snippet(user_id)
    except Exception:
        return messages
    if not snippet:
        return messages
    return _append_system_block(messages, snippet)


def _inject_workspace_bound_context(
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
    agent_id: str | None,
) -> list[dict[str, Any]]:
    if agent_id != "general" or not workspace or not isinstance(workspace, dict):
        return messages
    try:
        snippet = build_workspace_bound_snippet(workspace)
    except Exception:
        return messages
    if not snippet:
        return messages
    return _append_system_block(messages, snippet)


def _inject_workspace_retrieval_bootstrap(
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
    agent_id: str | None,
) -> list[dict[str, Any]]:
    """First user turn only: index stats, repo tree, retrieve_context hint."""
    if agent_id not in ("coding", "coding_plan"):
        return messages
    if not workspace or not isinstance(workspace, dict):
        return messages
    user_turns = sum(1 for m in messages if isinstance(m, dict) and m.get("role") == "user")
    if user_turns > 1:
        return messages
    try:
        snippet = build_retrieval_bootstrap_snippet(workspace)
    except Exception:
        return messages
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


def _inject_workspace_verify_hints(
    messages: list[dict[str, Any]],
    workspace: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Inject verify policy hints from workspace fields (DB-backed ``verify_command`` / ``verify_required``)."""
    if not workspace or not isinstance(workspace, dict):
        return messages
    lines: list[str] = []
    vc = workspace.get("verify_command")
    if isinstance(vc, str) and vc.strip():
        lines.append(
            "This workspace has a **verify** command (stored server-side) — run it with the "
            "`workspace_verify` tool (same allowlisting as `bash`) or manually: "
            f"`{vc.strip()}`"
        )
    if workspace.get("verify_required"):
        lines.append(
            "Policy: **verify_required** is enabled — run `workspace_verify` until it succeeds "
            "(exit code 0) before you finish with a final user-facing answer."
        )
    if not lines:
        return messages
    snippet = "\n".join(lines)
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
    Always merge the live registry tool list into the request for the local catalog provider.

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
    "Catalog lists every parameter name with type/enum stubs (not full schemas or TOOL_DESCRIPTION). "
    "When `required` is non-empty, never call the tool with `{}` — populate those fields. "
    "Include optional fields when the task or a tool error requires them (e.g. git_url, dashboard_id). "
    "After a failed call, that tool may appear with full schema in tools[] on the next LLM round only."
)


def _minimal_property_stub(prop_schema: dict[str, Any]) -> dict[str, Any]:
    """Type-only property entry for catalog mode (no TOOL_DESCRIPTION / long hints)."""
    if not isinstance(prop_schema, dict):
        return {"type": "string"}
    stub: dict[str, Any] = {}
    typ = prop_schema.get("type")
    if isinstance(typ, str) and typ.strip():
        stub["type"] = typ.strip()
    elif isinstance(prop_schema.get("enum"), list):
        stub["type"] = "string"
    else:
        stub["type"] = "string"
    enum = prop_schema.get("enum")
    if isinstance(enum, list) and enum:
        stub["enum"] = enum
    return stub


def _minimal_catalog_parameters(fn: dict[str, Any]) -> dict[str, Any]:
    """All property names + type stubs; ``required`` unchanged — compact but exposes optional fields too."""
    cand = fn.get("parameters")
    if not isinstance(cand, dict):
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    props_src = cand.get("properties") if isinstance(cand.get("properties"), dict) else {}
    required = [str(x).strip() for x in (cand.get("required") or []) if str(x).strip()]
    keys: set[str] = {str(k).strip() for k in props_src.keys() if str(k).strip()}
    keys.update(required)
    min_props = cand.get("minProperties")
    if isinstance(min_props, int) and min_props > 0 and not keys:
        keys = {str(k) for k in props_src.keys()}
    any_of = cand.get("anyOf")
    if isinstance(any_of, list):
        for branch in any_of:
            if not isinstance(branch, dict):
                continue
            branch_props = branch.get("properties")
            if isinstance(branch_props, dict):
                keys.update(str(k).strip() for k in branch_props.keys() if str(k).strip())
            for req in branch.get("required") or []:
                key = str(req).strip()
                if key:
                    keys.add(key)
    properties: dict[str, Any] = {}
    for key in sorted(keys):
        raw = props_src.get(key)
        properties[key] = _minimal_property_stub(raw) if isinstance(raw, dict) else {"type": "string"}
    out: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
    if required:
        out["required"] = required
    if isinstance(min_props, int) and min_props > 0:
        out["minProperties"] = min_props
    return out


def _full_schema_tool_function(name: str, fn: dict[str, Any]) -> dict[str, Any]:
    """OpenAI tools[] entry with registry ``parameters`` (required for unattended / schedule runs)."""
    desc = (fn.get("TOOL_DESCRIPTION") or fn.get("description") or "").strip()
    cand = fn.get("parameters")
    if isinstance(cand, dict) and cand.get("properties"):
        params: dict[str, Any] = copy.deepcopy(cand)
        if "type" not in params:
            params["type"] = "object"
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


def _catalog_tool_function(name: str, fn: dict[str, Any]) -> dict[str, Any]:
    """Small tools[] entry: TOOL_LABEL + TOOL_DESCRIPTION hint; minimal parameters (never full domain schemas)."""
    desc = (fn.get("TOOL_DESCRIPTION") or fn.get("description") or "").strip()
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
    elif name.startswith("mcp__"):
        cand = fn.get("parameters")
        if isinstance(cand, dict) and cand:
            params = cand
        else:
            params = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
    else:
        params = _minimal_catalog_parameters(fn)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": params,
        },
    }


def _tools_for_chat_request(
    merged_tools: list[Any],
    *,
    full_schema: bool = False,
) -> list[Any]:
    """
    Build tools[] for the LLM request.

    Default: **catalog** (required field stubs). **full_schema=True** only for reactive promotion paths.
    """
    builder = _full_schema_tool_function if full_schema else _catalog_tool_function
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
        out.append(builder(name, fn))
    return out


def _tools_payload_json_chars(tools: list[Any]) -> int:
    """Serialized ``tools[]`` JSON length (chars) for debug logs — not token count."""
    if not tools:
        return 0
    return len(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))
__all__ = [
    'AgentChatCancelled',
    'WorkspaceAccessDenied',
    '_AGENTS_AUTO_WORKSPACE_FROM_GIT_URL',
    '_CATALOG_PARAM_HINT',
    '_agent_behavior_flags',
    '_catalog_tool_function',
    '_coerce_body_bool',
    '_full_schema_tool_function',
    '_inject_agent_system_prompt',
    '_inject_dashboard_context',
    '_inject_system_prompt',
    '_inject_user_memory_context',
    '_inject_user_secrets_bootstrap',
    '_inject_workspace_bound_context',
    '_inject_workspace_retrieval_bootstrap',
    '_inject_workspace_verify_hints',
    '_merge_tools',
    '_parse_capability_hints',
    '_parse_disabled_tool_names',
    '_parse_router_categories_value',
    '_parse_router_category_tokens',
    '_permission_reply_user_message',
    '_tool_spec_name',
    '_tools_for_chat_request',
    '_tools_payload_json_chars',
    '_wait_for_tool_permission_reply',
]
