"""Agent turn hooks dispatch by tool_discipline_preset."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from apps.backend.domain.agent_runtime.turn_hooks import turn_hooks_for_agent
from apps.backend.domain.agent_runtime.dashboard_guards import DashboardTurnHooks


def test_turn_hooks_dashboard_preset(monkeypatch):
    monkeypatch.setattr(
        "apps.backend.domain.agent_runtime.turn_hooks._agent_behavior_flags",
        lambda aid: {"tool_discipline_preset": "dashboard"},
    )
    hooks = turn_hooks_for_agent("dashboard")
    assert isinstance(hooks, DashboardTurnHooks)


def test_turn_hooks_noop_for_general(monkeypatch):
    monkeypatch.setattr(
        "apps.backend.domain.agent_runtime.turn_hooks._agent_behavior_flags",
        lambda aid: {"tool_discipline_preset": None},
    )
    hooks = turn_hooks_for_agent("general")
    assert hooks.maybe_nudge_text_only_turn({}, allowed_names=frozenset(), round_i=0) is None
