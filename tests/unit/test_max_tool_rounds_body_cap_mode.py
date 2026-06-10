"""Body agent_max_tool_rounds honored when AGENT_MAX_TOOL_ROUNDS=0 (cap mode)."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.core import config


def _effective_max_rounds(raw: object) -> int:
    max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
    if raw is not None:
        try:
            client_v = int(raw)  # type: ignore[arg-type]
            if client_v <= 0:
                max_tool_rounds_eff = config.MAX_TOOL_ROUNDS
            else:
                upper = (
                    config.MAX_TOOL_ROUNDS
                    if config.MAX_TOOL_ROUNDS < config.MAX_TOOL_ROUNDS_CAP
                    else config.MAX_TOOL_ROUNDS_CAP
                )
                max_tool_rounds_eff = max(1, min(client_v, upper))
        except (TypeError, ValueError):
            pass
    return max_tool_rounds_eff


def test_body_cap_honored_in_cap_mode() -> None:
    with patch.object(config, "MAX_TOOL_ROUNDS", config.MAX_TOOL_ROUNDS_CAP):
        assert _effective_max_rounds(4) == 4
        assert _effective_max_rounds(99999) == config.MAX_TOOL_ROUNDS_CAP


def test_body_clamped_to_env_when_env_limited() -> None:
    with patch.object(config, "MAX_TOOL_ROUNDS", 8):
        assert _effective_max_rounds(20) == 8
