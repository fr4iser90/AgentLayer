"""Quality of a delegate ``assistant_excerpt`` — is it an answer or only tool chatter?"""

from __future__ import annotations

import json
import re

__all__ = ["delegate_excerpt_is_actionable"]

_TOOL_NAME_ONLY_RE = re.compile(
    r"^\s*(?:\[)?(?:read_file|search|glob|list_dir|git_read|repository\.read_file)(?:\])?\s*$",
    re.IGNORECASE,
)


def _delegate_excerpt_is_meta_only(text: str) -> bool:
    """Prose that describes tool use without an actual answer (path + excerpt, header, quote, etc.)."""
    t = (text or "").strip()
    if not t:
        return True
    if _TOOL_NAME_ONLY_RE.match(t):
        return True
    low = t.lower()
    if low in ("done", "ok", "success", "completed"):
        return True
    # Bracketed tool name with nothing else substantive
    if re.fullmatch(r"\[?(?:read_file|search|glob|list_dir)\]?", low):
        return True
    # Path mentioned but no delivered content (no colon/em-dash content, no markdown header, no quotes)
    has_path = bool(re.search(r"\.[a-z0-9]{1,8}\b", t, re.IGNORECASE))
    has_delivery = bool(
        re.search(r"\.[a-z0-9]{1,8}\b\s*[:—\-]\s*\S", t, re.IGNORECASE)
        or re.search(r"^#\s+\S", t, re.MULTILINE)
        or re.search(r'["\'].{2,}["\']', t)
        or re.search(r"\n\s*\S", t)
    )
    if has_path and not has_delivery and len(t) < 120:
        if re.search(r"\b(read|called|used|searched|grep|opened)\b", low):
            return True
    # Short status without file signal
    if len(t) < 35 and re.search(r"\b(read|called|used|tool|successfully)\b", low):
        if not has_path and not re.search(r"^#\s", t, re.MULTILINE):
            return True
    if re.search(r"\bthe command\b", low) and re.search(r"\bwill:\b", low):
        return True
    if re.search(r"\bwill:\s*$", low, re.MULTILINE):
        return True
    stripped = t.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict) and "command" in obj:
            return True
    if re.search(r'^[\s`]*\{[\s\n]*"command"\s*:', t, re.MULTILINE):
        return True
    return False


def delegate_excerpt_is_actionable(excerpt: str) -> bool:
    """True when a delegate assistant_excerpt is usable for the orchestrator reply (not markup/meta)."""
    from apps.backend.domain.agent_runtime.loop_guards import _agent_final_text_looks_like_placeholder_tool_markup

    t = (excerpt or "").strip()
    if len(t) < 2:
        return False
    if _agent_final_text_looks_like_placeholder_tool_markup(t):
        return False
    low = t.lower()
    if "tool-call markup instead of plain text" in low:
        return False
    if _delegate_excerpt_is_meta_only(t):
        return False
    return True
