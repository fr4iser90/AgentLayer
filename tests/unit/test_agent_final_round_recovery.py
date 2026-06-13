"""Tests for final-round placeholder / fake tool markup detection."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent import (
    _agent_final_text_looks_like_placeholder_tool_markup,
    _assistant_plain_text_from_message,
    _sanitize_final_completion_assistant_content,
    _strip_prose_fake_tool_markup,
)


class FinalRoundRecoveryHeuristicTests(unittest.TestCase):
    def test_detects_tool_call_xml(self) -> None:
        s = "Hello\n\n<tool_call>\n<function=coding_list_dir>\n</function>\n</tool_call>"
        self.assertTrue(_agent_final_text_looks_like_placeholder_tool_markup(s))

    def test_detects_function_tag(self) -> None:
        self.assertTrue(_agent_final_text_looks_like_placeholder_tool_markup("<function=bash>"))

    def test_good_markdown_false(self) -> None:
        self.assertFalse(
            _agent_final_text_looks_like_placeholder_tool_markup(
                "## Summary\nUsed `list_dir` on `.`; saw `apps/`.\n\nNext: open `ChatPage.tsx`."
            )
        )

    def test_detects_invoke_tag(self) -> None:
        self.assertTrue(
            _agent_final_text_looks_like_placeholder_tool_markup(
                '<invoke name="read_file"><parameter name="path">README.md</parameter></invoke>'
            )
        )

    def test_detects_command_json(self) -> None:
        self.assertTrue(
            _agent_final_text_looks_like_placeholder_tool_markup(
                '{"command": "head -n 1 README.md"}'
            )
        )

    def test_assistant_plain_text(self) -> None:
        msg = {"role": "assistant", "content": "  hi  \n"}
        self.assertEqual(_assistant_plain_text_from_message(msg), "hi")

    def test_strip_tool_call_block(self) -> None:
        raw = "Intro\n\n<tool_call>\n<function=coding_glob>\n</function>\n</tool_call>\n"
        self.assertEqual(_strip_prose_fake_tool_markup(raw).strip(), "Intro")

    def test_sanitize_completion_mutates_data(self) -> None:
        data = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hi\n\n<tool_call>\n<function=x>\n</function>\n</tool_call>",
                    }
                }
            ]
        }
        self.assertTrue(_sanitize_final_completion_assistant_content(data))
        c = data["choices"][0]["message"]["content"]
        self.assertNotIn("<tool_call", c.lower())
