"""Unit tests for chat message client_id / reasoning helpers."""

from __future__ import annotations

import unittest

from apps.backend.infrastructure.platform.conversation_common import (
    parse_client_message_id,
    parse_message_reasoning,
)


class TestChatMessageMeta(unittest.TestCase):
    def test_client_id_from_id(self) -> None:
        self.assertEqual(parse_client_message_id({"id": " abc "}), "abc")

    def test_client_id_from_client_message_id(self) -> None:
        self.assertEqual(
            parse_client_message_id({"client_message_id": "cid-1"}),
            "cid-1",
        )

    def test_client_id_rejects_empty(self) -> None:
        self.assertIsNone(parse_client_message_id({"id": "  "}))
        self.assertIsNone(parse_client_message_id({}))

    def test_reasoning_from_aliases(self) -> None:
        self.assertEqual(parse_message_reasoning({"reasoning": " think "}), "think")
        self.assertEqual(
            parse_message_reasoning({"reasoning_content": "r2"}),
            "r2",
        )
        self.assertIsNone(parse_message_reasoning({"reasoning": ""}))


if __name__ == "__main__":
    unittest.main()
