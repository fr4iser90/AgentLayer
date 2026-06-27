"""Conversation API body validation (agent_log v2 object vs legacy list)."""

from __future__ import annotations

import unittest

from apps.backend.api.conversations.controllers.conversations_api import ConversationCreateBody, ConversationUpdateBody


class TestConversationCreateBody(unittest.TestCase):
    def test_agent_log_legacy_list(self) -> None:
        body = ConversationCreateBody.model_validate(
            {"title": "t", "mode": "agent", "model": "m", "agent_log": []}
        )
        self.assertEqual(body.agent_log, [])

    def test_agent_log_v2_object(self) -> None:
        payload = {"v": 2, "current": [], "turns": []}
        body = ConversationCreateBody.model_validate(
            {"title": "New chat", "mode": "agent", "model": "x", "agent_log": payload}
        )
        self.assertEqual(body.agent_log, payload)

    def test_update_agent_log_v2_object(self) -> None:
        payload = {"v": 2, "current": [{"id": "1", "kind": "llm", "text": "hi"}], "turns": []}
        body = ConversationUpdateBody.model_validate({"agent_log": payload})
        self.assertEqual(body.agent_log, payload)

    def test_message_item_accepts_created_at(self) -> None:
        from apps.backend.api.conversations.controllers.conversations_api import MessageItem

        m = MessageItem.model_validate(
            {
                "role": "user",
                "content": "hi",
                "created_at": "2024-06-01T12:00:00+00:00",
            }
        )
        self.assertEqual(m.created_at, "2024-06-01T12:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
