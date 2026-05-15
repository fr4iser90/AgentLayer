"""Tests for ``user_visible_llm_transport_error``."""

from __future__ import annotations

import unittest

import httpx

from apps.backend.infrastructure.llm_user_errors import user_visible_llm_transport_error


class TestLlmUserErrors(unittest.TestCase):
    def test_read_timeout_is_friendly_no_trace(self) -> None:
        msg, log_exc = user_visible_llm_transport_error(httpx.ReadTimeout("timed out"))
        self.assertFalse(log_exc)
        self.assertIn("timeout", msg.lower())
        self.assertIn("reverse proxy", msg.lower())

    def test_connect_error(self) -> None:
        msg, log_exc = user_visible_llm_transport_error(httpx.ConnectError("refused"))
        self.assertFalse(log_exc)
        self.assertIn("connect", msg.lower())

    def test_unknown_logs_trace(self) -> None:
        msg, log_exc = user_visible_llm_transport_error(RuntimeError("boom"))
        self.assertTrue(log_exc)
        self.assertIn("unexpected", msg.lower())


if __name__ == "__main__":
    unittest.main()
