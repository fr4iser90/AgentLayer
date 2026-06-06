"""Sanitize assistant text for chat display; recover dashboard tools pasted as JSON."""

from __future__ import annotations

import json
import re
import uuid
from json import JSONDecoder
from typing import Any

from apps.backend.domain.agent_io import _parse_tool_intent_from_content, _text_blobs_from_message
from apps.backend.domain.tool_forward_policy import is_propose_layouts_tool
from apps.backend.infrastructure.stream_repetition_guard import guard_assistant_text

_SIMULATION_CUT_MARKERS: tuple[str, ...] = (
    "**warte auf benutzereingabe",
    "**benutzer:**",
    "**meine reaktion:**",
    "**meine reaktion",
    "**user input:**",
    "**user:**",
    "**plan für die nächste",
    "**ende.**",
    "(self-correction",
    "**(self-correction",
    "**(final output",
    "**(end of thought",
    "**(end)**",
    "<think>",
    "wait, i am the ai",
    "wait, i am generating",
)

_STRIP_TOOL_JSON_NAMES: frozenset[str] = frozenset(
    {
        "dashboard.read",
        "propose_layouts",
        "patch_layout",
        "patch_data",
        "list",
    }
)


def _truncate_at_simulation_markers(text: str) -> str:
    lower = text.lower()
    cut = len(text)
    for marker in _SIMULATION_CUT_MARKERS:
        idx = lower.find(marker)
        if idx >= 0:
            cut = min(cut, idx)
    return text[:cut].rstrip() if cut < len(text) else text


def _strip_thought_blocks(text: str) -> str:
    out = re.sub(r"\[Thought\][\s\S]*?(?=\n{2,}|\Z)", "", text, flags=re.IGNORECASE)
    out = re.sub(
        r"<think>[\s\S]*?(?:</think>|\Z)",
        "",
        out,
        flags=re.IGNORECASE,
    )
    return out


def _strip_embedded_tool_json_blobs(text: str) -> str:
    """Remove ``{"name": "propose_layouts", "arguments": {...}}`` style prose from display text."""
    if not text or "{" not in text:
        return text
    parts: list[str] = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start < 0:
            parts.append(text[i:])
            break
        parts.append(text[i:start])
        try:
            obj, consumed = JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError:
            parts.append(text[start])
            i = start + 1
            continue
        chunk = text[start : start + consumed]
        drop = False
        if isinstance(obj, dict):
            name = str(obj.get("name") or "").strip()
            if name in _STRIP_TOOL_JSON_NAMES or is_propose_layouts_tool(name):
                drop = True
            elif "proposals" in obj and isinstance(obj.get("proposals"), list):
                drop = True
        if drop:
            i = start + consumed
            continue
        parts.append(chunk)
        i = start + consumed
    return "".join(parts)


def sanitize_assistant_display_text(text: str, *, max_chars: int = 14_000) -> str:
    """Trim reasoning leaks, fake user dialogue, and pasted tool JSON for chat bubbles."""
    if not text:
        return text
    t = _strip_thought_blocks(text.strip())
    t = _truncate_at_simulation_markers(t)
    t = _strip_embedded_tool_json_blobs(t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    guarded, _ = guard_assistant_text(t)
    t = guarded.strip()
    if len(t) > max_chars:
        t = t[: max_chars - 40].rstrip() + "\n\n…"
    return t


def synthetic_dashboard_tool_calls_from_message(
    msg: dict[str, Any],
    *,
    allowed_tool_names: set[str],
) -> list[dict[str, Any]] | None:
    """
    When Qwen pastes ``propose_layouts`` JSON in assistant text, recover one wire-format tool_call.
    Dashboard agent only — not a global CONTENT_TOOL_FALLBACK.
    """
    if "propose_layouts" not in allowed_tool_names:
        return None
    for blob in _text_blobs_from_message(msg):
        parsed = _parse_tool_intent_from_content(blob)
        if not parsed:
            continue
        name, params = parsed
        if not is_propose_layouts_tool(name):
            continue
        proposals = params.get("proposals")
        if not isinstance(proposals, list) or not proposals:
            continue
        return [
            {
                "id": f"recovered-{uuid.uuid4().hex[:16]}",
                "type": "function",
                "function": {
                    "name": "propose_layouts",
                    "arguments": json.dumps(params, ensure_ascii=False, default=str),
                },
            }
        ]
    return None


def sanitize_completion_for_dashboard_agent(data: dict[str, Any]) -> bool:
    """Mutate ``choices[0].message.content`` for cleaner embedded chat display."""
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
        cleaned = sanitize_assistant_display_text(raw)
        if cleaned == raw:
            return False
        msg["content"] = cleaned or "(empty)"
        ch0["message"] = msg
        ch_list[0] = ch0
        return True
    except (TypeError, KeyError, IndexError):
        return False
