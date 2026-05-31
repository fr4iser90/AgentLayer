"""Unit tests for Coding-style identical tool-call loop guard."""

from __future__ import annotations  

import unittest

from apps.backend.domain.agent import _AGENT_TOOL_DOOM_LOOP_HINT, _agent_tool_doom_loop_tick


class AgentToolDoomLoopTickTests(unittest.TestCase):
    def test_resets_on_different_args(self) -> None:
        ex = frozenset()
        k, n, h = _agent_tool_doom_loop_tick(
            None, 0, tool_name="t", args={"a": 1}, max_streak=3, exclude_names=ex
        )
        self.assertEqual(h, None)
        self.assertEqual(n, 1)
        k2, n2, h2 = _agent_tool_doom_loop_tick(k, n, tool_name="t", args={"a": 2}, max_streak=3, exclude_names=ex)
        self.assertIsNone(h2)
        self.assertEqual(n2, 1)

    def test_fires_on_third_repeat_for_non_excluded_tool(self) -> None:
        """Mutating / risky tools still trigger doom (use ``bash``; reads are excluded by default)."""
        args = {"command": "pwd"}
        ex = frozenset()
        k, n, h = _agent_tool_doom_loop_tick(
            None, 0, tool_name="bash", args=args, max_streak=3, exclude_names=ex
        )
        self.assertIsNone(h)
        self.assertEqual(n, 1)
        k, n, h = _agent_tool_doom_loop_tick(k, n, tool_name="bash", args=args, max_streak=3, exclude_names=ex)
        self.assertIsNone(h)
        self.assertEqual(n, 2)
        k, n, h = _agent_tool_doom_loop_tick(k, n, tool_name="bash", args=args, max_streak=3, exclude_names=ex)
        self.assertEqual(h, _AGENT_TOOL_DOOM_LOOP_HINT)
        self.assertIsNone(k)
        self.assertEqual(n, 0)

    def test_excluded_read_tools_never_advance_doom(self) -> None:
        ex = frozenset({"read_file"})
        args = {"path": "README.md"}
        k, n, h = _agent_tool_doom_loop_tick(
            None, 0, tool_name="read_file", args=args, max_streak=3, exclude_names=ex
        )
        self.assertIsNone(h)
        self.assertEqual(n, 0)
        self.assertIsNone(k)
        k2, n2, h2 = _agent_tool_doom_loop_tick(
            k, n, tool_name="read_file", args=args, max_streak=3, exclude_names=ex
        )
        self.assertIsNone(h2)
        self.assertEqual(n2, 0)
