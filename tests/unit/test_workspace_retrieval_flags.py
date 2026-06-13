"""Workspace retrieval / index flag helpers."""

from __future__ import annotations

import json
import unittest

from plugins.tools.workspace.lib.common import workspace_retrieval_flags
from plugins.tools.workspace.search.retrieve_context import retrieve_context


class TestWorkspaceRetrievalFlags(unittest.TestCase):
    def test_flags_from_context(self) -> None:
        ctx = {
            "workspace": {
                "id": "00000000-0000-0000-0000-000000000001",
                "path": "/tmp/ws",
                "semantic_index_enabled": False,
                "retrieval_enabled": True,
            }
        }
        sem, ret = workspace_retrieval_flags(ctx)
        self.assertFalse(sem)
        self.assertTrue(ret)

    def test_retrieve_context_skipped_when_retrieval_off(self) -> None:
        ctx = {
            "workspace": {
                "id": "00000000-0000-0000-0000-000000000001",
                "path": "/tmp/ws",
                "retrieval_enabled": False,
            }
        }
        raw = retrieve_context({"query": "auth middleware"}, context=ctx)
        data = json.loads(raw)
        self.assertFalse(data.get("ok"))
        self.assertEqual(data.get("reason"), "retrieval_disabled")


if __name__ == "__main__":
    unittest.main()
