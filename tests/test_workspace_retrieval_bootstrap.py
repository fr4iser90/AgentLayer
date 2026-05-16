"""Workspace retrieval bootstrap and staleness."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
    build_retrieval_bootstrap_snippet,
    is_index_stale,
    list_repo_top_level,
)


class TestWorkspaceRetrievalBootstrap(unittest.TestCase):
    def test_never_indexed_is_stale(self) -> None:
        ws = {"semantic_index_enabled": True, "last_index_at": None}
        self.assertTrue(is_index_stale(ws))

    def test_snippet_mentions_retrieve_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "README.md").write_text("hi\n", encoding="utf-8")
            snip = build_retrieval_bootstrap_snippet(
                {
                    "name": "demo",
                    "path": str(root),
                    "semantic_index_enabled": True,
                    "retrieval_enabled": True,
                    "last_index_at": None,
                }
            )
        self.assertIn("retrieve_context", snip)
        self.assertIn("Top-level:", snip)

    def test_list_repo_top_level_skips_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "src").mkdir()
            names = list_repo_top_level(root)
        self.assertIn("src/", names)
        self.assertFalse(any(n.startswith(".") for n in names))

    def test_stale_when_head_newer_than_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "f.py").write_text("x = 1\n", encoding="utf-8")
            import subprocess

            subprocess.run(["git", "init"], cwd=root, capture_output=True, check=False)
            subprocess.run(["git", "add", "f.py"], cwd=root, capture_output=True, check=False)
            subprocess.run(
                ["git", "commit", "-m", "init", "--author", "t <t@t>"],
                cwd=root,
                capture_output=True,
                env={
                    **dict(__import__("os").environ),
                    "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
                    "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00",
                },
                check=False,
            )
            ws = {
                "path": str(root),
                "semantic_index_enabled": True,
                "last_index_at": "2019-06-01T00:00:00+00:00",
            }
            self.assertTrue(is_index_stale(ws))

    def test_maybe_schedule_respects_flag(self) -> None:
        from apps.backend.infrastructure.workspace_retrieval_bootstrap import (
            maybe_schedule_index_on_attach,
        )

        ws = {
            "id": "00000000-0000-0000-0000-000000000001",
            "path": "/tmp/x",
            "semantic_index_enabled": True,
            "access_role": "owner",
            "last_index_at": None,
        }
        with patch(
            "apps.backend.core.config.config.AGENT_WORKSPACE_INDEX_ON_ATTACH",
            False,
        ):
            self.assertFalse(maybe_schedule_index_on_attach(ws))


if __name__ == "__main__":
    unittest.main()
