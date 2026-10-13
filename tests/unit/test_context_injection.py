"""Context injection ledger for transparent chat badges + LLM omit."""

from __future__ import annotations

import unittest

from apps.backend.domain.agent_runtime.context_injection import (
    begin_inject_ledger,
    clear_omitable_digests,
    inject_omit_stub,
    record_injection,
    take_inject_digests,
    take_inject_ledger,
    take_omitted_injects,
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
        take_inject_digests()
        take_omitted_injects()
        self.assertEqual(len(public), 2)
        self.assertEqual(public[0]["kind"], "agent_system_prompt")
        self.assertEqual(public[1]["kind"], "agents_md")
        self.assertIn("npm test", public[1]["body"])
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("npm test", msgs[0]["content"])

    def test_repeat_without_omit_still_lists_sent_blocks(self) -> None:
        body = "# Project\nUse npm test."
        tok1 = begin_inject_ledger()
        _append_system_block([], body, kind="agents_md", label="AGENTS.md")
        take_inject_ledger(tok1)
        digests = take_inject_digests()
        take_omitted_injects()
        self.assertIn("agents_md", digests)

        tok2 = begin_inject_ledger(prior_digests=digests)
        msgs2 = _append_system_block([], body, kind="agents_md", label="AGENTS.md")
        public2 = take_inject_ledger(tok2)
        take_inject_digests()
        take_omitted_injects()
        # Omit off → still sent → still shown (with body).
        self.assertEqual(len(public2), 1)
        self.assertIn("npm test", public2[0]["body"])
        self.assertIn("npm test", msgs2[0]["content"])

    def test_omit_hides_from_ui_ledger(self) -> None:
        body = "# Project\nUse npm test."
        tok1 = begin_inject_ledger(skip_llm_when_unchanged=True)
        msgs1 = _append_system_block([], body, kind="agents_md", label="AGENTS.md")
        take_inject_ledger(tok1)
        digests = take_inject_digests()
        take_omitted_injects()
        self.assertIn("npm test", msgs1[0]["content"])

        tok2 = begin_inject_ledger(prior_digests=digests, skip_llm_when_unchanged=True)
        msgs2 = _append_system_block(
            [{"role": "user", "content": "hi"}],
            body,
            kind="agents_md",
            label="AGENTS.md",
        )
        public2 = take_inject_ledger(tok2)
        omitted = take_omitted_injects()
        take_inject_digests()
        self.assertEqual(public2, [])
        self.assertEqual(len(msgs2), 1)
        self.assertEqual(msgs2[0]["role"], "user")
        self.assertEqual(len(omitted), 1)
        self.assertEqual(omitted[0][0], "agents_md")
        stub = inject_omit_stub(omitted)
        self.assertIn("AGENTS.md", stub)

    def test_always_send_kinds_listed_when_resent(self) -> None:
        body = "You are coding."
        tok1 = begin_inject_ledger(skip_llm_when_unchanged=True)
        _append_system_block([], body, kind="agent_system_prompt", label="Agent system prompt")
        take_inject_ledger(tok1)
        digests = take_inject_digests()
        take_omitted_injects()

        tok2 = begin_inject_ledger(prior_digests=digests, skip_llm_when_unchanged=True)
        msgs2 = _append_system_block([], body, kind="agent_system_prompt", label="Agent system prompt")
        public2 = take_inject_ledger(tok2)
        omitted = take_omitted_injects()
        take_inject_digests()
        self.assertEqual(len(public2), 1)
        self.assertIn("You are coding", public2[0]["body"])
        self.assertIn("You are coding", msgs2[0]["content"])
        self.assertEqual(omitted, [])

    def test_clear_omitable_keeps_always_send_digests(self) -> None:
        cleared = clear_omitable_digests(
            {"agents_md": "aaa", "agent_system_prompt": "bbb", "persona": "ccc"}
        )
        self.assertNotIn("agents_md", cleared)
        self.assertEqual(cleared.get("agent_system_prompt"), "bbb")
        self.assertEqual(cleared.get("persona"), "ccc")

    def test_noop_without_ledger(self) -> None:
        record_injection("agents_md", "should not appear")
        tok = begin_inject_ledger()
        public = take_inject_ledger(tok)
        take_inject_digests()
        take_omitted_injects()
        self.assertEqual(public, [])


if __name__ == "__main__":
    unittest.main()
