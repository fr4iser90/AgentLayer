"""User context for chat: structured profile + free-form persona (no credentials)."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Protocol

logger = logging.getLogger(__name__)

MAX_PERSONA_CHARS = 8000
MAX_PROFILE_SUMMARY_CHARS = 6000


class UserPersonaDependencies(Protocol):
    def user_agent_profile_get(self, user_id: uuid.UUID) -> dict[str, Any] | None: ...

    def user_persona_get(self, user_id: uuid.UUID) -> dict[str, Any] | None: ...


_deps: UserPersonaDependencies | None = None


def register_user_persona_dependencies(deps: UserPersonaDependencies) -> None:
    global _deps
    _deps = deps


class _UserPersonaDbPort:
    def user_agent_profile_get(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        return _deps.user_agent_profile_get(user_id) if _deps is not None else None

    def user_persona_get(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        return _deps.user_persona_get(user_id) if _deps is not None else None


db = _UserPersonaDbPort()

# Normalized interaction_style → system hint (also pass raw value as reference).
INTERACTION_STYLE_HINTS: dict[str, str] = {
    "assistant": (
        "Interaction mode: assistant — respond when asked; minimize unsolicited output "
        "unless proactive_mode allows it."
    ),
    "coach": (
        "Interaction mode: coach — offer practical tips, options, and next steps when helpful."
    ),
    "operator": (
        "Interaction mode: operator — prefer concrete actions and tool calls to finish tasks."
    ),
    "companion": "Interaction mode: companion — warm, conversational tone.",
}


def _append_system_block(messages: list[dict[str, Any]], block: str) -> list[dict[str, Any]]:
    out = list(messages)
    if not block.strip():
        return out
    if not out:
        return [{"role": "system", "content": block.strip()}]
    if out[0].get("role") == "system":
        existing = out[0].get("content") or ""
        out[0] = {
            **out[0],
            "content": (existing + "\n\n" + block).strip(),
        }
    else:
        out.insert(0, {"role": "system", "content": block.strip()})
    return out


def _want_injection_section(prefs: dict[str, Any], key: str) -> bool:
    """
    If ``injection_preferences`` is empty, all sections are allowed (subject to
    per-field emptiness). If it contains ``include_*`` keys, explicit ``false``
    hides that section; omitted keys default to true.
    """
    if not prefs:
        return True
    if key not in prefs:
        return True
    return bool(prefs[key]) is not False


def _format_weighted_tags(items: Any) -> str | None:
    if not isinstance(items, list) or not items:
        return None
    pairs: list[tuple[str, float]] = []
    for x in items:
        if isinstance(x, dict) and (x.get("name") or "").strip():
            try:
                w = float(x.get("weight", 1.0))
            except (TypeError, ValueError):
                w = 1.0
            w = max(0.0, min(1.0, w))
            pairs.append((str(x["name"]).strip(), w))
        elif isinstance(x, str) and x.strip():
            pairs.append((x.strip(), 1.0))
    if not pairs:
        return None
    pairs.sort(key=lambda t: -t[1])
    parts: list[str] = []
    for name, w in pairs[:40]:
        parts.append(f"{name} ({w:.1f})" if w != 1.0 else name)
    return ", ".join(parts)


def format_agent_profile_summary(prof: dict[str, Any]) -> str:
    """
    Compact bullet list — only non-empty fields. Optional ``injection_preferences``
    keys: include_identity, include_location, include_communication, include_interests,
    include_work, include_tools, include_behavior, include_usage_patterns,
    include_dynamic_traits, include_known_people
    (only applies when inject_dynamic_traits is true).
    """
    if bool(prof.get("inject_structured_profile")) is False:
        return ""
    prefs = prof.get("injection_preferences") or {}
    if not isinstance(prefs, dict):
        prefs = {}

    lines: list[str] = ["User profile:"]

    def add(label: str, val: Any) -> None:
        if val is None:
            return
        if isinstance(val, str) and not val.strip():
            return
        if isinstance(val, (list, dict)) and not val:
            return
        lines.append(f"- {label}: {val}")

    if _want_injection_section(prefs, "include_identity"):
        add("Name", prof.get("display_name"))
        add("Output language", prof.get("preferred_output_language"))
        add("Locale", prof.get("locale"))
        add("Timezone", prof.get("timezone"))

        # Known people / friends context
        # NOTE: Known people are NOT injected by default anymore
        # They are available via the dedicated `info` tool which the agent will call ONLY when needed
        # This prevents ~1-2k token overhead in every single chat request

    if _want_injection_section(prefs, "include_location"):
        add("Home location", prof.get("home_location"))
        add("Work location", prof.get("work_location"))
        add("Travel mode", prof.get("travel_mode"))
        tp = prof.get("travel_preferences") or {}
        if isinstance(tp, dict) and tp:
            snippet = json.dumps(tp, ensure_ascii=False)
            if len(snippet) > 800:
                snippet = snippet[:800] + "…"
            add("Travel preferences", snippet)

    if _want_injection_section(prefs, "include_communication"):
        add("Tone", prof.get("tone"))
        add("Verbosity", prof.get("verbosity"))
        add("Language / detail level", prof.get("language_level"))

    if _want_injection_section(prefs, "include_interests"):
        ti = _format_weighted_tags(prof.get("interests"))
        th = _format_weighted_tags(prof.get("hobbies"))
        add("Interests", ti)
        add("Hobbies", th)

    if _want_injection_section(prefs, "include_work"):
        add("Job title", prof.get("job_title"))
        add("Organization", prof.get("organization"))
        add("Industry", prof.get("industry"))
        add("Experience level", prof.get("experience_level"))

    if _want_injection_section(prefs, "include_tools"):
        pt = prof.get("primary_tools") or []
        if isinstance(pt, list) and pt:
            add(
                "Primary tools / stack",
                ", ".join(str(x) for x in pt[:50] if str(x).strip()),
            )

    if _want_injection_section(prefs, "include_behavior"):
        lines.append(
            "- Proactive suggestions: "
            + ("yes" if prof.get("proactive_mode") else "no (reactive unless asked)")
        )
        raw_style = (prof.get("interaction_style") or "").strip().lower()
        if raw_style:
            hint = INTERACTION_STYLE_HINTS.get(raw_style)
            if hint:
                lines.append(f"- {hint}")
            else:
                add("Interaction style (custom)", raw_style)

    if _want_injection_section(prefs, "include_usage_patterns"):
        up = prof.get("usage_patterns") or {}
        if isinstance(up, dict) and up:
            snippet = json.dumps(up, ensure_ascii=False)
            if len(snippet) > 1000:
                snippet = snippet[:1000] + "…"
            add("Usage patterns", snippet)

    traits_ok = bool(prof.get("inject_dynamic_traits"))
    if prefs and isinstance(prefs, dict):
        if "include_dynamic_traits" in prefs:
            traits_ok = traits_ok and bool(prefs.get("include_dynamic_traits"))
    if traits_ok:
        dt = prof.get("dynamic_traits") or {}
        if isinstance(dt, dict) and dt:
            snippet = json.dumps(dt, ensure_ascii=False)
            if len(snippet) > 1200:
                snippet = snippet[:1200] + "…"
            add("Learned traits (system)", snippet)

    if len(lines) <= 1:
        return ""
    body = "\n".join(lines)
    if len(body) > MAX_PROFILE_SUMMARY_CHARS:
        body = body[:MAX_PROFILE_SUMMARY_CHARS] + "\n… (truncated)"
    return body


def apply_user_persona_system(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Merge structured ``user_agent_profile`` (if enabled) and free-text
    ``user_agent_persona.instructions`` (if enabled) into the system message.

    Secrets must never be stored here — use ``/v1/user/secrets`` + tools only.
    """
    from apps.backend.domain.shared.identity import get_identity

    _tid, uid = get_identity()
    if uid is None:
        return messages

    blocks: list[str] = []

    try:
        prof = db.user_agent_profile_get(uid)
    except Exception:
        logger.debug("user_agent_profile_get failed (migrations?)", exc_info=True)
        prof = None
    if prof:
        summary = format_agent_profile_summary(prof)
        if summary:
            blocks.append(summary)

    try:
        row = db.user_persona_get(uid)
    except Exception:
        logger.debug("user_persona_get failed (schema not migrated?)", exc_info=True)
        row = None
    if row and row.get("inject_into_agent"):
        instr = (row.get("instructions") or "").strip()
        if instr:
            if len(instr) > MAX_PERSONA_CHARS:
                instr = instr[:MAX_PERSONA_CHARS] + "\n… (truncated)"
            blocks.append(
                "User-provided notes (not credentials). "
                "Honor when consistent with safety and policy:\n\n" + instr
            )

    if not blocks:
        return messages

    combined = "\n\n".join(blocks)
    return _append_system_block(messages, combined)
