"""Unit tests for E2E mock LLM responses."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from apps.backend.infrastructure.e2e_mock_llm import (
    build_mock_chat_completion,
    e2e_mock_llm_enabled,
)
from apps.backend.infrastructure.openai_compat_http import http_post_chat_completions


class TestE2eMockLlm(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_E2E_MOCK_LLM", None)
            self.assertFalse(e2e_mock_llm_enabled())

    def test_first_round_tool_call(self) -> None:
        body = {
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "coding_list_dir"}}],
        }
        data = build_mock_chat_completion(body)
        msg = data["choices"][0]["message"]
        self.assertTrue(msg.get("tool_calls"))
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "coding_list_dir")
        args = json.loads(msg["tool_calls"][0]["function"]["arguments"])
        self.assertEqual(args.get("path"), ".")

    def test_second_round_plain_text(self) -> None:
        body = {
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "coding_list_dir", "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "x", "content": "[]"},
            ],
            "tools": [{"type": "function", "function": {"name": "coding_list_dir"}}],
        }
        data = build_mock_chat_completion(body)
        msg = data["choices"][0]["message"]
        self.assertIn("E2E mock", msg.get("content") or "")

    def test_http_post_short_circuit(self) -> None:
        with patch.dict(os.environ, {"AGENT_E2E_MOCK_LLM": "1"}):
            data, omitted = http_post_chat_completions(
                "http://unused/v1/chat/completions",
                {"messages": [{"role": "user", "content": "x"}], "tools": [{}]},
            )
        self.assertFalse(omitted)
        self.assertTrue(data["choices"][0]["message"].get("tool_calls"))


if __name__ == "__main__":
    unittest.main()
