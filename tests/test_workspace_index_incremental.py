from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

class TestScanPaths(unittest.TestCase):
    def test_scan_paths_indexes_single_file(self) -> None:
        from plugins.tools.capabilities.coding.coding_index_lib import _HAS_TS, get_index

        if not _HAS_TS:
            self.skipTest("tree-sitter not installed")

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fp = root / "hello.py"
            fp.write_text("def greet():\n    return 1\n", encoding="utf-8")
            idx = get_index()
            entries, stats = idx.scan_paths(root, ["hello.py"])
            self.assertEqual(stats["scanned"], 1)
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].symbols)


class TestIncrementalEnqueue(unittest.TestCase):
    def test_enqueue_off_mode_is_noop(self) -> None:
        from apps.backend.infrastructure import workspace_index_incremental as inc

        inc._PENDING.clear()
        with mock.patch(
            "apps.backend.infrastructure.workspace_index_incremental.config.AGENT_WORKSPACE_INDEX_ON_WRITE",
            "off",
        ):
            inc.enqueue_incremental_index(
                "ws-1",
                "/tmp",
                ["a.py"],
                workspace={"index_on_write": "off"},
            )
            self.assertEqual(inc._PENDING, {})

    def test_enqueue_debounced_batches_paths(self) -> None:
        from apps.backend.infrastructure import workspace_index_incremental as inc

        with mock.patch(
            "apps.backend.infrastructure.workspace_index_incremental.config.AGENT_WORKSPACE_INDEX_ON_WRITE",
            "debounced",
        ):
            with mock.patch(
                "apps.backend.infrastructure.workspace_index_incremental.config.AGENT_WORKSPACE_INDEX_DEBOUNCE_SEC",
                99,
            ):
                with mock.patch.object(inc, "_full_index_running", return_value=False):
                    with mock.patch("threading.Timer") as timer_cls:
                        timer_cls.return_value = mock.Mock()
                        inc._PENDING.clear()
                        inc.enqueue_incremental_index(str(uuid.uuid4()), "/tmp/ws", ["a.py", "b.py"])
                        self.assertEqual(len(inc._PENDING), 1)
                        entry = next(iter(inc._PENDING.values()))
                        self.assertEqual(entry["paths"], {"a.py", "b.py"})
                        timer_cls.assert_called_once()


class TestRunIncrementalIndex(unittest.TestCase):
    def test_run_incremental_skips_when_semantic_off(self) -> None:
        from apps.backend.infrastructure.workspace_retrieval import run_incremental_index

        out = run_incremental_index(
            str(uuid.uuid4()),
            "/nonexistent",
            ["x.py"],
            semantic_index_enabled=False,
        )
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("reason"), "semantic_index_disabled")


if __name__ == "__main__":
    unittest.main()
