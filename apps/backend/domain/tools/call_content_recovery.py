"""Recover wire-format ``tool_calls`` from assistant prose / fake markup when models skip native tool calling."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from apps.backend.domain.agent_runtime.tool_call_parsing import (
    _extract_first_json_object,
    _parse_named_parenthesized_tool_call,
    _parse_tool_intent_from_content,
    _resolve_meta_tool_name,
    _text_blobs_from_message,
)
from apps.backend.domain.agent_runtime.tool_schema import (
    _args_effectively_empty,
    _infer_tool_args_from_message,
    _tool_schema_names_match,
    _unwrap_tool_args_aliases,
)

logger = logging.getLogger(__name__)

_FAKE_FUNCTION_BLOCK_RE = re.compile(
    r"<function\s*=\s*([^>\s/]+)\s*>(.*?)</function>",
    re.IGNORECASE | re.DOTALL,
)
_FAKE_FUNCTION_SELF_CLOSE_RE = re.compile(
    r"<function\s*=\s*([^>\s/]+)\s*/?\s*>",
    re.IGNORECASE,
)
_INVOKE_BLOCK_RE = re.compile(
    r'<invoke\s+name=["\']([^"\']+)["\']\s*>(.*?)</invoke>',
    re.IGNORECASE | re.DOTALL,
)
_PARAMETER_TAG_RE = re.compile(
    r'<parameter\s+name=["\']([^"\']+)["\']\s*>(.*?)</parameter>',
    re.IGNORECASE | re.DOTALL,
)


def _resolve_to_allowed_name(raw: str, allowed: set[str]) -> str | None:
    name = (raw or "").strip()
    if not name:
        return None
    if name in allowed:
        return name
    qualified = _resolve_meta_tool_name(name)
    if qualified in allowed:
        return qualified
    for candidate in allowed:
        if _tool_schema_names_match(name, candidate):
            return candidate
        if _tool_schema_names_match(qualified, candidate):
            return candidate
    if name.startswith("workspaces."):
        alt = "workspace." + name[len("workspaces.") :]
        if alt in allowed:
            return alt
    return None


def _params_from_markup_body(body: str) -> dict[str, Any]:
    text = (body or "").strip()
    if not text:
        return {}
    params: dict[str, Any] = {}
    for match in _PARAMETER_TAG_RE.finditer(text):
        params[match.group(1).strip()] = match.group(2).strip()
    if params:
        return params
    obj = _extract_first_json_object(text)
    return dict(obj) if isinstance(obj, dict) else {}


def _parse_fake_markup_tool_call(text: str) -> tuple[str, dict[str, Any]] | None:
    block = _FAKE_FUNCTION_BLOCK_RE.search(text)
    if block:
        return block.group(1).strip(), _params_from_markup_body(block.group(2))
    self_close = _FAKE_FUNCTION_SELF_CLOSE_RE.search(text)
    if self_close:
        return self_close.group(1).strip(), {}
    invoke = _INVOKE_BLOCK_RE.search(text)
    if invoke:
        return invoke.group(1).strip(), _params_from_markup_body(invoke.group(2))
    return None


def _parse_parenthesized_for_allowed(
    text: str, allowed: set[str]
) -> tuple[str, dict[str, Any]] | None:
    for name in sorted(allowed, key=len, reverse=True):
        args = _parse_named_parenthesized_tool_call(text, name)
        if isinstance(args, dict):
            return name, args
        if "." in name:
            short = name.rsplit(".", 1)[-1]
            args = _parse_named_parenthesized_tool_call(text, short)
            if isinstance(args, dict):
                return name, args
    return None


def _normalize_recovered_args(
    tool_name: str,
    params: dict[str, Any] | None,
    msg: dict[str, Any],
) -> dict[str, Any]:
    out = _unwrap_tool_args_aliases(dict(params or {}))
    if _args_effectively_empty(out):
        inferred = _infer_tool_args_from_message(tool_name, msg)
        if inferred:
            out = _unwrap_tool_args_aliases(inferred)
    return out


def _wire_tool_call(tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"recovered-{uuid.uuid4().hex[:16]}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(params, ensure_ascii=False, default=str),
        },
    }


def _try_recover_from_blob(
    blob: str,
    *,
    allowed: set[str],
    msg: dict[str, Any],
) -> tuple[dict[str, Any], str] | None:
    text = (blob or "").strip()
    if not text:
        return None

    parsed = _parse_tool_intent_from_content(text)
    if parsed:
        raw_name, params = parsed
        resolved = _resolve_to_allowed_name(raw_name, allowed)
        if resolved:
            args = _normalize_recovered_args(resolved, params, msg)
            return _wire_tool_call(resolved, args), "content_json"

    paren = _parse_parenthesized_for_allowed(text, allowed)
    if paren:
        resolved_name, params = paren
        args = _normalize_recovered_args(resolved_name, params, msg)
        return _wire_tool_call(resolved_name, args), "parenthesized"

    markup = _parse_fake_markup_tool_call(text)
    if markup:
        raw_name, params = markup
        resolved = _resolve_to_allowed_name(raw_name, allowed)
        if resolved:
            args = _normalize_recovered_args(resolved, params, msg)
            return _wire_tool_call(resolved, args), "fake_markup"

    return None


def recover_tool_calls_from_assistant_content(
    msg: dict[str, Any],
    *,
    allowed_tool_names: set[str] | frozenset[str],
) -> list[dict[str, Any]] | None:
    """
    Build synthetic ``tool_calls`` when the model wrote tool intent in text instead of the API field.
    Only tools present in ``allowed_tool_names`` are recovered.
    """
    allowed = {str(n).strip() for n in allowed_tool_names if str(n).strip()}
    if not allowed:
        return None

    for blob in _text_blobs_from_message(msg):
        hit = _try_recover_from_blob(blob, allowed=allowed, msg=msg)
        if hit:
            wire, pattern = hit
            logger.info(
                "tool_call_content_recovery: recovered tool=%r via pattern=%s",
                wire["function"]["name"],
                pattern,
            )
            return [wire]
    return None
