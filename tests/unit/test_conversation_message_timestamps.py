"""Per-message created_at round-trip for chat conversations."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from apps.backend.infrastructure.platform.conversations_db import _parse_message_created_at


class TestConversationMessageTimestamps(unittest.TestCase):
    def test_parse_iso_z(self) -> None:
        dt = _parse_message_created_at("2024-06-01T12:30:00Z")
        assert dt is not None
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_unix_ms(self) -> None:
        ms = 1_700_000_000_000
        dt = _parse_message_created_at(ms)
        assert dt is not None
        self.assertEqual(int(dt.timestamp() * 1000), ms)

    def test_parse_datetime_naive_as_utc(self) -> None:
        naive = datetime(2024, 1, 2, 3, 4, 5)
        dt = _parse_message_created_at(naive)
        assert dt is not None
        self.assertEqual(dt.tzinfo, timezone.utc)

    def test_parse_invalid_returns_none(self) -> None:
        self.assertIsNone(_parse_message_created_at("not-a-date"))
        self.assertIsNone(_parse_message_created_at(""))
        self.assertIsNone(_parse_message_created_at(None))


if __name__ == "__main__":
    unittest.main()
