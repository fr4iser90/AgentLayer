"""Generic tool-arg recovery from assistant prose (no per-tool user-text guessing)."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent import _normalize_tool_call_arguments


class AgentToolArgProseRecoveryTests(unittest.TestCase):
    def test_bash_recovered_when_model_writes_json_in_prose(self) -> None:
        assistant = {
            "role": "assistant",
            "content": 'Next: bash({"command": "git pull --ff-only"})',
        }
        out = _normalize_tool_call_arguments("bash", {}, assistant, [], None)
        self.assertEqual(out.get("command"), "git pull --ff-only")

    def test_empty_bash_stays_empty_without_prose(self) -> None:
        msgs = [{"role": "user", "content": "git pull (ff-only), update docs."}]
        assistant = {"role": "assistant", "content": ""}
        out = _normalize_tool_call_arguments("bash", {}, assistant, msgs, None)
        self.assertFalse(str(out.get("command") or "").strip())
