from __future__ import annotations

import json
import logging
from json import JSONDecoder
from typing import Any

from apps.backend.domain.agent_runtime.tool_catalog import _tool_spec_name
from apps.backend.domain.plugin_system.registry import get_registry

logger = logging.getLogger(__name__)


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
    """Single-line summary for logs/events - from plugin ``tool_step_detail`` when defined."""
    from apps.backend.domain.tools.step_label import recap_line_for_tool

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
    Remove whole-line angle-bracket sentinels some models emit so prose tool calls can be parsed.
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
    """Parse ``tool_name({...})`` from assistant prose."""
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
    """Parse ``read_tool({...})`` / ``replace_tool({...})`` style text."""
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
    resolved = get_registry().resolve_domain_tool("tool_factory", base)
    return resolved or f"tool_factory.{base}"


def _resolve_meta_tool_name(name: str) -> str:
    """Map short tool_factory names to qualified registry names when needed."""
    if name in {"read", "replace", "create", "update", "rename", "list"}:
        return _resolve_tool_factory_name(name)
    return name


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
    Some models emit JSON like {\"tool\": \"<name>\", \"parameters\": {...}} in message content.
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
    """Collect strings where models may hide JSON tool intent."""
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
        "reasoning_content_delta",
    ):
        v = msg.get(key)
        if isinstance(v, str) and v.strip():
            blobs.append(v)
    return blobs


__all__ = [
    "_CONTENT_META_TOOL_NAMES",
    "_CONTENT_META_TOP_LEVEL_ARG_KEYS",
    "_coerce_params_dict",
    "_extract_first_json_object",
    "_format_normalized_tool_args_for_recap",
    "_known_tool_names",
    "_merge_meta_tool_obj_args",
    "_parse_named_parenthesized_tool_call",
    "_parse_parenthesized_tool_call",
    "_parse_tool_arguments",
    "_parse_tool_intent_from_content",
    "_resolve_meta_tool_name",
    "_resolve_tool_factory_name",
    "_strip_model_output_markers",
    "_text_blobs_from_message",
    "_unwrap_fenced_json",
]
