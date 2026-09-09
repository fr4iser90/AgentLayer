"""Tests for dashboard board-file MIME sniffing and text decode."""

from __future__ import annotations

import base64
import unittest

from apps.backend.infrastructure.dashboards.dashboard_upload_bytes import (
    decode_text_payload,
    is_image_mime,
    is_text_like_mime,
    sniff_image_mime,
    sniff_upload_mime,
)

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class TestSniffUploadMime(unittest.TestCase):
    def test_png_magic(self) -> None:
        self.assertEqual(sniff_image_mime(_TINY_PNG[:64]), "image/png")
        self.assertEqual(sniff_upload_mime(_TINY_PNG, filename="x.png"), "image/png")
        self.assertTrue(is_image_mime("image/png"))

    def test_markdown_by_extension(self) -> None:
        data = b"# Hello\n\nWorld\n"
        self.assertEqual(
            sniff_upload_mime(data, filename="notes.md", declared="application/octet-stream"),
            "text/markdown",
        )
        self.assertTrue(is_text_like_mime("text/markdown"))

    def test_plain_text_by_extension(self) -> None:
        data = b"plain text"
        self.assertEqual(sniff_upload_mime(data, filename="a.txt"), "text/plain")

    def test_rejects_binary_as_markdown(self) -> None:
        data = b"\xff\xfe\x00\x01not utf8 \x80\x81"
        self.assertIsNone(sniff_upload_mime(data, filename="bad.md"))

    def test_decode_text(self) -> None:
        self.assertEqual(decode_text_payload("café".encode("utf-8")), "café")
        self.assertIsNone(decode_text_payload(b"\xff\xfe"))


if __name__ == "__main__":
    unittest.main()
