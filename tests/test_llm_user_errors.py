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

    def test_connect_error_mentions_chat_not_embeddings(self) -> None:
        msg, log_exc = user_visible_llm_transport_error(httpx.ConnectError("refused"))
        self.assertFalse(log_exc)
        self.assertIn("chat", msg.lower())
        self.assertIn("embedding_base_url", msg.lower())

    def test_connect_error_includes_post_url_when_request_present(self) -> None:
        req = httpx.Request("POST", "http://192.168.1.5:11435/v1/chat/completions")
        exc = httpx.ConnectError("All connection attempts failed", request=req)
        msg, log_exc = user_visible_llm_transport_error(exc)
        self.assertFalse(log_exc)
        self.assertIn("192.168.1.5", msg)
        self.assertIn("chat/completions", msg)

    def test_unknown_logs_trace(self) -> None:
        msg, log_exc = user_visible_llm_transport_error(RuntimeError("boom"))
        self.assertTrue(log_exc)
        self.assertIn("unexpected", msg.lower())


if __name__ == "__main__":
    unittest.main()
