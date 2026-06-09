"""Unit tests for tool-loop budget / reminder helper strings."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent import (
    _agent_final_round_text_only_hint,
    _agent_near_max_tool_rounds_reminder,
    _agent_tool_budget_system_message,
)


class AgentToolBudgetMessageTests(unittest.TestCase):
    def test_budget_includes_cap(self) -> None:
        s = _agent_tool_budget_system_message(20)
        self.assertIn("20", s)
        self.assertIn("Round 20", s)
        self.assertIn("Round 19", s)

    def test_budget_single_round(self) -> None:
        s = _agent_tool_budget_system_message(1)
        self.assertIn("one", s.lower())

    def test_near_max_mentions_rounds(self) -> None:
        s = _agent_near_max_tool_rounds_reminder(18, 20)
        self.assertIn("18", s)
        self.assertIn("20", s)
        self.assertIn("19", s)

    def test_final_hint(self) -> None:
        s = _agent_final_round_text_only_hint(20, 20)
        self.assertIn("20", s)
        self.assertIn("synthesize", s.lower())
        self.assertIn("follow-up", s.lower())
