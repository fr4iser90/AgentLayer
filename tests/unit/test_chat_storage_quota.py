"""Unit tests for chat storage / session quotas."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from apps.backend.infrastructure.platform import chat_storage_quota as q


class TestEstimatePayloadBytes(unittest.TestCase):
    def test_counts_content_and_reasoning(self) -> None:
        n = q.estimate_payload_bytes(
            [{"role": "assistant", "content": "hi", "reasoning": "think"}],
            {"v": 2, "current": [], "turns": []},
        )
        self.assertGreater(n, 0)

    def test_empty(self) -> None:
        self.assertEqual(q.estimate_payload_bytes(None, None), 0)


class TestAssertConversationSize(unittest.TestCase):
    def test_blocks_when_projected_over_limit(self) -> None:
        with patch.object(q, "max_conversation_bytes", return_value=10):
            with self.assertRaises(ValueError):
                q.assert_conversation_size_allowed(
                    conversation_id=None,
                    messages=[{"role": "user", "content": "x" * 100}],
                    agent_log=None,
                )

    def test_warn_flag_near_limit(self) -> None:
        with patch.object(q, "max_conversation_bytes", return_value=100):
            snap = q.assert_conversation_size_allowed(
                conversation_id=None,
                messages=[{"role": "user", "content": "x" * 85}],
                agent_log=None,
            )
            self.assertTrue(snap["warn"])
            self.assertFalse(snap["over_limit"])


class TestPublicFields(unittest.TestCase):
    def test_public_defaults(self) -> None:
        with patch.object(
            q,
            "_operator_chat_quota_row",
            return_value={
                "chat_max_conversation_mb": 2048,
                "chat_max_personal_sessions": 100,
                "chat_max_dashboard_sessions": 30,
            },
        ):
            pub = q.chat_quota_settings_public_fields()
            self.assertEqual(pub["chat_max_conversation_mb"], 2048)
            self.assertEqual(pub["chat_warn_ratio"], 0.8)


if __name__ == "__main__":
    unittest.main()
