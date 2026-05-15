"""Regression: fill empty ``coding_bash`` from user text (GGUF empty JSON)."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent import _normalize_tool_call_arguments


class AgentCodingBashUserInferTests(unittest.TestCase):
    def test_git_pull_from_german_user_message(self) -> None:
        msgs = [
            {
                "role": "user",
                "content": (
                    "kannst du mal schauen das project ist nicht up to date, ich würde da gerne was changen , "
                    "aber vorher muss das geupdated werden also pull denk ich mal oder?"
                ),
            }
        ]
        assistant = {"role": "assistant", "content": ""}
        out = _normalize_tool_call_arguments("coding_bash", {}, assistant, msgs, None)
        self.assertEqual(out.get("command"), "git pull")

    def test_explicit_git_pull_in_user_message(self) -> None:
        msgs = [{"role": "user", "content": "git pull"}]
        assistant = {"role": "assistant", "content": ""}
        out = _normalize_tool_call_arguments("coding_bash", {}, assistant, msgs, None)
        self.assertEqual(out.get("command"), "git pull")
