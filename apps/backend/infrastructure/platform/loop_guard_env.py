"""Env bootstrap for advisory tool/output echo loop guards."""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


AGENT_TOOL_THRASH_ENABLED = _env_bool("AGENT_TOOL_THRASH_ENABLED", True)
AGENT_TOOL_THRASH_STREAK_MAX = max(2, _env_int("AGENT_TOOL_THRASH_STREAK_MAX", 5))
AGENT_TOOL_DOOM_LOOP_ENABLED = _env_bool("AGENT_TOOL_DOOM_LOOP_ENABLED", True)
AGENT_TOOL_DOOM_LOOP_STREAK_MAX = max(2, _env_int("AGENT_TOOL_DOOM_LOOP_STREAK_MAX", 5))
AGENT_TOOL_REPEAT_ADVICE_THRESHOLDS: tuple[int, ...] = tuple(
    sorted(
        {
            int(p)
            for p in (os.environ.get("AGENT_TOOL_REPEAT_ADVICE_THRESHOLDS") or "3,5,8").split(",")
            if p.strip().isdigit() and int(p.strip()) >= 2
        }
    )
) or (3, 5, 8)
AGENT_ASSISTANT_OUTPUT_ECHO_ENABLED = _env_bool("AGENT_ASSISTANT_OUTPUT_ECHO_ENABLED", True)
AGENT_ASSISTANT_OUTPUT_ECHO_STREAK_MAX = max(2, _env_int("AGENT_ASSISTANT_OUTPUT_ECHO_STREAK_MAX", 3))
AGENT_ASSISTANT_OUTPUT_ECHO_MIN_CHARS = max(40, _env_int("AGENT_ASSISTANT_OUTPUT_ECHO_MIN_CHARS", 80))
AGENT_TOOL_RESULT_ECHO_ENABLED = _env_bool("AGENT_TOOL_RESULT_ECHO_ENABLED", True)
AGENT_TOOL_RESULT_ECHO_STREAK_MAX = max(2, _env_int("AGENT_TOOL_RESULT_ECHO_STREAK_MAX", 5))
AGENT_TOOL_RESULT_ECHO_MIN_CHARS = max(20, _env_int("AGENT_TOOL_RESULT_ECHO_MIN_CHARS", 40))
