from __future__ import annotations

import copy
import json
import logging
from typing import Any

from apps.backend.domain.plugin_system.registry import get_registry

logger = logging.getLogger(__name__)

_CATALOG_PARAM_HINT = (
    "Catalog lists every parameter name with type/enum stubs (not full schemas or TOOL_DESCRIPTION). "
    "When `required` is non-empty, never call the tool with `{}` — populate those fields. "
    "Include optional fields when the task or a tool error requires them (e.g. git_url, dashboard_id). "
    "After a failed call, that tool may appear with full schema in tools[] on the next LLM round only."
)


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
    """All property names + type stubs; ``required`` unchanged."""
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
    """OpenAI tools[] entry with registry ``parameters``."""
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
    """Small tools[] entry: TOOL_LABEL + TOOL_DESCRIPTION hint; minimal parameters."""
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

    Default: catalog mode. ``full_schema=True`` only for reactive promotion paths.
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
    """Serialized ``tools[]`` JSON length (chars) for debug logs - not token count."""
    if not tools:
        return 0
    return len(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))


__all__ = [
    "_CATALOG_PARAM_HINT",
    "_catalog_tool_function",
    "_full_schema_tool_function",
    "_merge_tools",
    "_minimal_catalog_parameters",
    "_tool_spec_name",
    "_tools_for_chat_request",
    "_tools_payload_json_chars",
]
