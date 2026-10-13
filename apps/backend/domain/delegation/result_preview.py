"""Human-readable preview of tool results for chat run cards (bash output, delegate excerpt)."""

from __future__ import annotations

import json

__all__ = ["tool_result_display_line"]

_RESULT_DISPLAY_MAX = 4000


def _tail_for_display(text: str, max_chars: int = _RESULT_DISPLAY_MAX) -> str:
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars + 2
    return f"…(+{omitted} chars)\n" + text[-(max_chars - 2) :]


def _is_bash_tool(name: str) -> bool:
    n = (name or "").strip().lower()
    return n == "bash" or n.endswith(".bash") or n == "coding_bash"


def _bash_tool_result_display(raw: str) -> str | None:
    """Stdout/stderr preview for chat run cards (already secret-redacted by the tool)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _tail_for_display(raw) or None
    if not isinstance(data, dict):
        return _tail_for_display(raw) or None
    parts: list[str] = []
    exit_code = data.get("exit_code")
    if exit_code is not None:
        try:
            parts.append(f"exit {int(exit_code)}")
        except (TypeError, ValueError):
            parts.append(f"exit {exit_code}")
    if data.get("ok") is False:
        err = data.get("error")
        if isinstance(err, str) and err.strip():
            parts.append(err.strip())
    out = data.get("output")
    if isinstance(out, str) and out.strip() and out.strip() != "(no output)":
        body = out.strip()
        if data.get("truncated") is True:
            body = f"(truncated)\n{body}"
        parts.append(body)
    if not parts:
        return None
    return _tail_for_display("\n".join(parts))


def tool_result_display_line(tool_name: str, result: str) -> str | None:
    """
    Human-readable preview for WS ``result_display`` (chat run cards / benchmarks).

    - ``bash``: command ``output`` (+ exit / error), tailed
    - ``delegate``: ``assistant_excerpt`` on success, ``error`` on failure
    """
    name = (tool_name or "").strip()
    raw = (result or "").strip()
    if not raw:
        return None
    if _is_bash_tool(name):
        return _bash_tool_result_display(raw)
    if name != "delegate" and not name.endswith(".delegate"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("ok") is False:
        err = data.get("error")
        return str(err).strip()[:500] if isinstance(err, str) and err.strip() else "failed"
    ex = data.get("assistant_excerpt")
    if isinstance(ex, str) and ex.strip():
        return ex.strip()[:500]
    return None
