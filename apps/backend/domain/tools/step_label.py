"""Build chat UI tool step labels from plugin ``TOOL_LABEL`` + ``tool_step_detail`` hooks."""

from __future__ import annotations

from typing import Any

_STEP_LABEL_DETAIL_MAX = 200


def _truncate(text: str, max_len: int = _STEP_LABEL_DETAIL_MAX) -> str:
    t = (text or "").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def registry_label_for_tool(tool_name: str) -> str | None:
    try:
        from apps.backend.domain.plugin_system.registry import get_registry

        return get_registry().display_label_for_tool(tool_name)
    except Exception:
        return None


def detail_from_tool(tool_name: str, args: dict[str, Any]) -> str:
    """Detail line from the tool plugin's optional ``tool_step_detail(arguments)``."""
    try:
        from apps.backend.domain.plugin_system.registry import get_registry

        return _truncate(get_registry().tool_step_detail_for(tool_name, args))
    except Exception:
        return ""


def format_tool_step_label_from_args(
    tool_name: str,
    args: dict[str, Any],
    *,
    tool_label: str | None = None,
) -> str:
    """``TOOL_LABEL`` + plugin ``tool_step_detail`` — no central arg key lists."""
    name = (tool_name or "").strip()
    verb = (tool_label or "").strip() or registry_label_for_tool(name)
    if not verb:
        verb = name.replace("_", " ") if name else "Tool"
    detail = detail_from_tool(name, args or {})
    return f"{verb} {detail}".strip() if detail else verb


def recap_line_for_tool(tool_name: str, args: dict[str, Any], *, max_len: int = 400) -> str:
    """Log/recap line: plugin detail hook, else compact args JSON."""
    detail = detail_from_tool(tool_name, args)
    if detail:
        return _truncate(detail, max_len)
    norm = dict(args or {})
    if not norm:
        return "(empty)"
    import json

    try:
        line = json.dumps(norm, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        line = repr(norm)
    line = line.replace("\n", " ")
    return _truncate(line, max_len)
