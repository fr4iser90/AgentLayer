"""coding_search engine selection (python walk vs optional ripgrep)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plugins.tools.agent.core.coding.coding_search import coding_search


class TestCodingSearchEngines(unittest.TestCase):
    def test_python_engine_finds_substring(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("hello_unique_marker_99\n", encoding="utf-8")
            ctx = {"workspace": {"id": "00000000-0000-0000-0000-000000000099", "path": str(root)}}
            with patch(
                "plugins.tools.agent.core.coding.coding_search._global_config.AGENT_CODING_SEARCH_USE_RIPGREP",
                False,
            ):
                out = coding_search({"query": "hello_unique_marker_99"}, context=ctx)
            data = json.loads(out)
            self.assertTrue(data.get("ok"), msg=data)
            self.assertEqual(data.get("search_engine"), "python")
            self.assertTrue(any("a.py" in m.get("path", "") for m in data.get("matches") or []))

    def test_ripgrep_engine_when_available(self) -> None:
        import shutil

        if not shutil.which("rg"):
            self.skipTest("ripgrep not installed")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.py").write_text("rg_marker_xyzzy\n", encoding="utf-8")
            ctx = {"workspace": {"id": "00000000-0000-0000-0000-000000000088", "path": str(root)}}
            out = coding_search({"query": "rg_marker_xyzzy"}, context=ctx)
            data = json.loads(out)
            self.assertTrue(data.get("ok"), msg=data)
            self.assertEqual(data.get("search_engine"), "ripgrep")
            self.assertTrue(any("b.py" in m.get("path", "") for m in data.get("matches") or []))


if __name__ == "__main__":
    unittest.main()
