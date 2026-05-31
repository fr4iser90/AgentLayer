"""Regression: fill empty ``bash`` from user text (GGUF empty JSON)."""

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
        out = _normalize_tool_call_arguments("bash", {}, assistant, msgs, None)
        self.assertEqual(out.get("command"), "git pull")

    def test_explicit_git_pull_in_user_message(self) -> None:
        msgs = [{"role": "user", "content": "git pull"}]
        assistant = {"role": "assistant", "content": ""}
        out = _normalize_tool_call_arguments("bash", {}, assistant, msgs, None)
        self.assertEqual(out.get("command"), "git pull")

    def test_unattended_empty_bash_stays_empty(self) -> None:
        msgs = [{"role": "user", "content": "Run scheduled task with git pull (ff-only)."}]
        assistant = {"role": "assistant", "content": "Git pull succeeded. Now I need to:"}
        ctx = {"agent_unattended": True}
        out = _normalize_tool_call_arguments("bash", {}, assistant, msgs, ctx)
        self.assertFalse(str(out.get("command") or "").strip())

    def test_git_pull_ff_only_stops_at_comma(self) -> None:
        from apps.backend.domain.agent import _infer_shell_command_from_user_text

        cmd = _infer_shell_command_from_user_text(
            "git pull (ff-only), update docs/MAINTENANCE_REPORT.md"
        )
        self.assertEqual(cmd, "git pull --ff-only")
