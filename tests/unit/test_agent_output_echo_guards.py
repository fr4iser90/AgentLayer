"""Unit tests for identical assistant / tool-result output loop guards (advisory)."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent_runtime.loop_guards import (
    _AGENT_OUTPUT_ECHO_HINT,
    _agent_assistant_output_echo_tick,
    _agent_tool_result_echo_tick,
)


class AssistantOutputEchoTickTests(unittest.TestCase):
    def test_ignores_short_content(self) -> None:
        k, n, h = _agent_assistant_output_echo_tick(
            None, 0, content="ok", thresholds=(3, 5, 8), min_chars=80
        )
        self.assertIsNone(k)
        self.assertEqual(n, 0)
        self.assertIsNone(h)

    def test_advisory_on_third_identical_block_keeps_chain(self) -> None:
        block = "A" * 100
        k, n, h = _agent_assistant_output_echo_tick(
            None, 0, content=block, thresholds=(3, 5), min_chars=80
        )
        self.assertIsNone(h)
        self.assertEqual(n, 1)
        k, n, h = _agent_assistant_output_echo_tick(
            k, n, content=block, thresholds=(3, 5), min_chars=80
        )
        self.assertIsNone(h)
        self.assertEqual(n, 2)
        k, n, h = _agent_assistant_output_echo_tick(
            k, n, content=block, thresholds=(3, 5), min_chars=80
        )
        self.assertEqual(h, _AGENT_OUTPUT_ECHO_HINT)
        self.assertEqual(n, 3)
        self.assertIsNotNone(k)

    def test_resets_on_different_content(self) -> None:
        a = "A" * 100
        b = "B" * 100
        k, n, _ = _agent_assistant_output_echo_tick(
            None, 0, content=a, thresholds=(3,), min_chars=80
        )
        k2, n2, h2 = _agent_assistant_output_echo_tick(
            k, n, content=b, thresholds=(3,), min_chars=80
        )
        self.assertEqual(n2, 1)
        self.assertIsNone(h2)
        self.assertNotEqual(k2, k)


class ToolResultEchoTickTests(unittest.TestCase):
    def test_advisory_on_identical_result_streak(self) -> None:
        body = '{"ok":true,"content":"' + ("x" * 80) + '"}'
        k, n, h = _agent_tool_result_echo_tick(
            None, 0, tool_name="read_file", result=body, thresholds=(3,), min_chars=40
        )
        self.assertEqual(n, 1)
        k, n, h = _agent_tool_result_echo_tick(
            k, n, tool_name="read_file", result=body, thresholds=(3,), min_chars=40
        )
        self.assertEqual(n, 2)
        k, n, h = _agent_tool_result_echo_tick(
            k, n, tool_name="read_file", result=body, thresholds=(3,), min_chars=40
        )
        self.assertEqual(h, _AGENT_OUTPUT_ECHO_HINT)
        self.assertEqual(n, 3)

    def test_different_tools_do_not_share_streak(self) -> None:
        body = '{"ok":true,"content":"' + ("y" * 80) + '"}'
        k, n, _ = _agent_tool_result_echo_tick(
            None, 0, tool_name="read_file", result=body, thresholds=(3,), min_chars=40
        )
        k2, n2, h2 = _agent_tool_result_echo_tick(
            k, n, tool_name="bash", result=body, thresholds=(3,), min_chars=40
        )
        self.assertEqual(n2, 1)
        self.assertIsNone(h2)
        self.assertNotEqual(k2, k)


if __name__ == "__main__":
    unittest.main()
