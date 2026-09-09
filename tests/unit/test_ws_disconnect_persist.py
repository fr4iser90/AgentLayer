"""Unit tests for WS disconnect assistant persistence helper."""

from __future__ import annotations

import uuid
import unittest
from unittest.mock import patch

from apps.backend.api.chat.controllers.chat_websocket import (
    _ensure_ws_user_message,
    _persist_ws_assistant_completion,
)


class TestPersistWsAssistantCompletion(unittest.TestCase):
    def test_appends_assistant_reply(self) -> None:
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        data = {"choices": [{"message": {"content": "  hello from agent  "}}]}
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
            return_value=True,
        ) as m:
            _persist_ws_assistant_completion(uid, {"conversation_id": str(cid)}, data)
            m.assert_called_once_with(
                uid, cid, role="assistant", content="hello from agent"
            )

    def test_skips_without_conversation_id(self) -> None:
        uid = uuid.uuid4()
        data = {"choices": [{"message": {"content": "hi"}}]}
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
        ) as m:
            _persist_ws_assistant_completion(uid, {}, data)
            m.assert_not_called()

    def test_skips_invalid_conversation_id(self) -> None:
        uid = uuid.uuid4()
        data = {"choices": [{"message": {"content": "hi"}}]}
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
        ) as m:
            _persist_ws_assistant_completion(uid, {"conversation_id": "not-a-uuid"}, data)
            m.assert_not_called()

    def test_skips_error_shaped_reply(self) -> None:
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        data = {"error": "boom"}
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
        ) as m:
            _persist_ws_assistant_completion(uid, {"conversation_id": str(cid)}, data)
            m.assert_not_called()


class TestEnsureWsUserMessage(unittest.TestCase):
    def test_appends_when_missing(self) -> None:
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        work = {
            "conversation_id": str(cid),
            "messages": [{"role": "user", "content": "please run this"}],
        }
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_get",
            return_value={"messages": []},
        ), patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
            return_value=True,
        ) as m:
            _ensure_ws_user_message(uid, work)
            m.assert_called_once_with(
                uid, cid, role="user", content="please run this"
            )

    def test_skips_when_already_present(self) -> None:
        uid = uuid.uuid4()
        cid = uuid.uuid4()
        work = {
            "conversation_id": str(cid),
            "messages": [{"role": "user", "content": "please run this"}],
        }
        with patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_get",
            return_value={"messages": [{"role": "user", "content": "please run this"}]},
        ), patch(
            "apps.backend.api.chat.controllers.chat_websocket.conversation_append_message",
        ) as m:
            _ensure_ws_user_message(uid, work)
            m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
