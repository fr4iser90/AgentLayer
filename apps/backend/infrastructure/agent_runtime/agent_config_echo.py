"""Effective config getters for assistant/tool-result echo loop guards."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.platform import config as app_config


def assistant_output_echo_enabled(*, tenant_id: int | None = None) -> bool:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_bool(
        "agent.assistant_output_echo_enabled",
        tenant_id=tenant_id,
        default=app_config.AGENT_ASSISTANT_OUTPUT_ECHO_ENABLED,
    )


def assistant_output_echo_streak_max(*, tenant_id: int | None = None) -> int:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_int(
        "agent.assistant_output_echo_streak_max",
        tenant_id=tenant_id,
        default=app_config.AGENT_ASSISTANT_OUTPUT_ECHO_STREAK_MAX,
        minimum=2,
    )


def assistant_output_echo_min_chars(*, tenant_id: int | None = None) -> int:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_int(
        "agent.assistant_output_echo_min_chars",
        tenant_id=tenant_id,
        default=app_config.AGENT_ASSISTANT_OUTPUT_ECHO_MIN_CHARS,
        minimum=40,
    )


def tool_result_echo_enabled(*, tenant_id: int | None = None) -> bool:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_bool(
        "agent.tool_result_echo_enabled",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOL_RESULT_ECHO_ENABLED,
    )


def tool_result_echo_streak_max(*, tenant_id: int | None = None) -> int:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_int(
        "agent.tool_result_echo_streak_max",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOL_RESULT_ECHO_STREAK_MAX,
        minimum=2,
    )


def tool_result_echo_min_chars(*, tenant_id: int | None = None) -> int:
    from apps.backend.infrastructure.agent_runtime import agent_config_effective as ace

    return ace.effective_int(
        "agent.tool_result_echo_min_chars",
        tenant_id=tenant_id,
        default=app_config.AGENT_TOOL_RESULT_ECHO_MIN_CHARS,
        minimum=20,
    )


def display_echo_value(knob_id: str, *, tenant_id: int | None) -> tuple[Any, str] | None:
    """Return (value, source) for echo knobs, or None if ``knob_id`` is unrelated."""
    if knob_id == "agent.assistant_output_echo_enabled":
        return assistant_output_echo_enabled(tenant_id=tenant_id), "implicit_default"
    if knob_id == "agent.assistant_output_echo_streak_max":
        return assistant_output_echo_streak_max(tenant_id=tenant_id), "implicit_default"
    if knob_id == "agent.assistant_output_echo_min_chars":
        return assistant_output_echo_min_chars(tenant_id=tenant_id), "implicit_default"
    if knob_id == "agent.tool_result_echo_enabled":
        return tool_result_echo_enabled(tenant_id=tenant_id), "implicit_default"
    if knob_id == "agent.tool_result_echo_streak_max":
        return tool_result_echo_streak_max(tenant_id=tenant_id), "implicit_default"
    if knob_id == "agent.tool_result_echo_min_chars":
        return tool_result_echo_min_chars(tenant_id=tenant_id), "implicit_default"
    return None
