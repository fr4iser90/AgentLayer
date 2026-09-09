"""Context injection ledger for transparent chat badges."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent_runtime.context_injection import (
    begin_inject_ledger,
    record_injection,
    take_inject_ledger,
)
from apps.backend.domain.agent_runtime.persona import _append_system_block


class TestContextInjectionLedger(unittest.TestCase):
    def test_records_append_system_block(self) -> None:
        tok = begin_inject_ledger()
        msgs = _append_system_block(
            [],
            "You are coding.",
            kind="agent_system_prompt",
            label="Agent system prompt (coding)",
        )
        msgs = _append_system_block(msgs, "# Project\nUse npm test.", kind="agents_md", label="AGENTS.md")
        public = take_inject_ledger(tok)
        self.assertEqual(len(public), 2)
        self.assertEqual(public[0]["kind"], "agent_system_prompt")
        self.assertEqual(public[1]["kind"], "agents_md")
        self.assertIn("npm test", public[1]["body"])
        self.assertEqual(msgs[0]["role"], "system")

    def test_noop_without_ledger(self) -> None:
        record_injection("agents_md", "should not appear")
        # no crash; nothing to take
        tok = begin_inject_ledger()
        public = take_inject_ledger(tok)
        self.assertEqual(public, [])


if __name__ == "__main__":
    unittest.main()
