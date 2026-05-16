"""Ripgrep line parsing (trailing colon in matched source)."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from plugins.tools.capabilities.coding.coding_search import _parse_ripgrep_line, coding_search


class TestRipgrepLineParse(unittest.TestCase):
    def test_parse_trailing_colon_in_source(self) -> None:
        line = "/tmp/app.py:6:def login_handler(username, password):"
        parsed = _parse_ripgrep_line(line)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        path, lineno, text = parsed
        self.assertTrue(path.endswith("app.py"))
        self.assertEqual(lineno, 6)
        self.assertIn("login_handler", text)

    def test_ripgrep_finds_def_with_trailing_colon(self) -> None:
        if not shutil.which("rg"):
            self.skipTest("ripgrep not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "routes.py").write_text(
                "def login_handler(username, password):\n    pass\n",
                encoding="utf-8",
            )
            ctx = {"workspace": {"id": "00000000-0000-0000-0000-000000000001", "path": str(root)}}
            out = json.loads(coding_search({"query": "login_handler"}, context=ctx))
            self.assertTrue(out.get("ok"), msg=out)
            matches = out.get("matches") or []
            self.assertGreaterEqual(len(matches), 1)
            self.assertIn("login_handler", matches[0].get("text", ""))


if __name__ == "__main__":
    unittest.main()
