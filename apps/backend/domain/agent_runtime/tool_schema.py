from __future__ import annotations

import copy
import json
import logging
from typing import Any

from apps.backend.domain.agent_runtime.tool_call_parsing import (
    _extract_first_json_object,
    _parse_named_parenthesized_tool_call,
    _text_blobs_from_message,
)
from apps.backend.domain.plugin_system.registry import get_registry

logger = logging.getLogger(__name__)

PLANNER_NO_EXTRA_HINTS_AFTER_TOOL = frozenset(
    {
        "settings_patch",
        "settings_get",
        "get_tool_help",
    }
)


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
    """Short system nudge when models emit tool_calls without required JSON fields."""
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
    """Exact registered tool name only - no fuzzy suffix match (``create`` != ``workspace.create``)."""
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
            "Do not emit wire-format `tool_calls` with `{}` - pass the schema fields in `arguments`."
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
            "Fix the next `tool_calls[].function.arguments` JSON - do not call the tool with `{}`."
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
    """Promote a tool to full schema on the next LLM round."""
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
    """Unwrap aliased tool JSON nesting only - wire arguments are never inferred from prose."""
    _ = (name, assistant_msg, messages, tool_context)
    return _unwrap_tool_args_aliases(dict(args))


__all__ = [
    "PLANNER_NO_EXTRA_HINTS_AFTER_TOOL",
    "_arg_value_present",
    "_args_effectively_empty",
    "_infer_tool_args_from_message",
    "_lookup_tool_parameter_schema",
    "_normalize_tool_call_arguments",
    "_registry_tool_spec_by_registered_name",
    "_tool_error_suggests_incomplete_arguments",
    "_tool_parameter_recovery_hint",
    "_tool_schema_names_match",
    "_unwrap_tool_args_aliases",
    "format_tool_call_validation_error",
    "tool_call_warrants_full_schema_promotion",
    "validate_tool_call_arguments",
]
