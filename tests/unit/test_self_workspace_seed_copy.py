from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path


class SeedCopyIgnoreTest(unittest.TestCase):
    """The seed -> user-workspace copy must not swallow its own destination.

    Live incident this guards against: ``AGENTLAYER_WORKSPACE_PATH`` is a
    bind mount whose host location sits inside the repo used as the
    ``agentlayer-self`` seed. A plain ``shutil.copytree`` then copies the
    destination into itself and recurses until ``ENAMETOOLONG``. Inside
    the container the two paths look unrelated
    (``/workspace/AgentLayer`` vs ``/data/project_workspaces``), so only
    an identity check on ``(st_dev, st_ino)`` catches it.
    """

    def _make_seed(self, base: Path) -> Path:
        seed = base / "repo"
        (seed / ".git").mkdir(parents=True)
        (seed / ".git" / "HEAD").write_text("ref: refs/heads/main", encoding="utf-8")
        (seed / "apps").mkdir()
        (seed / "apps" / "main.py").write_text("print('x')\n", encoding="utf-8")

        # Regenerable build artifacts that must never be dragged along.
        (seed / "node_modules" / "pkg").mkdir(parents=True)
        (seed / "node_modules" / "pkg" / "index.js").write_text("x", encoding="utf-8")
        (seed / "output" / "run").mkdir(parents=True)
        (seed / "output" / "run" / "a.log").write_text("x", encoding="utf-8")
        (seed / "__pycache__").mkdir()
        (seed / "__pycache__" / "mod.pyc").write_text("x", encoding="utf-8")
        (seed / ".pytest_cache" / "v").mkdir(parents=True)
        (seed / ".pytest_cache" / "v" / "cache").write_text("x", encoding="utf-8")
        return seed

    def _copy_with_env(self, seed: Path, target: Path, ws_base: Path) -> None:
        from apps.backend.infrastructure.workspace import workspace_service as ws

        old = os.environ.get("AGENTLAYER_WORKSPACE_PATH")
        os.environ["AGENTLAYER_WORKSPACE_PATH"] = str(ws_base)
        try:
            shutil.copytree(seed, target, ignore=ws._seed_copy_ignore(seed, target))
        finally:
            if old is None:
                os.environ.pop("AGENTLAYER_WORKSPACE_PATH", None)
            else:
                os.environ["AGENTLAYER_WORKSPACE_PATH"] = old

    def test_workspace_base_nested_in_seed_is_not_copied(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = self._make_seed(base)

            # The hazard, laid out exactly as the compose bind mounts do:
            # the workspace base lives inside the seed tree, and the
            # target lives inside the workspace base.
            ws_base = seed / "workspace"
            ws_base.mkdir()
            target = ws_base / "u1" / "agentlayer-self"
            target.parent.mkdir(parents=True)

            self._copy_with_env(seed, target, ws_base)

            self.assertFalse(
                (target / "workspace").exists(),
                "the workspace base must never be copied into the target",
            )
            # And nothing may have self-nested below the target.
            self.assertEqual(list(target.glob("**/agentlayer-self")), [])
            # Real source still arrives.
            self.assertTrue((target / "apps" / "main.py").exists())

    def test_build_artifacts_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = self._make_seed(base)
            ws_base = base / "workspaces"
            ws_base.mkdir()
            target = ws_base / "u1" / "agentlayer-self"
            target.parent.mkdir(parents=True)

            self._copy_with_env(seed, target, ws_base)

            for junk in ("node_modules", "output", "__pycache__", ".pytest_cache"):
                self.assertFalse(
                    (target / junk).exists(),
                    f"{junk} must not be copied into a user workspace",
                )

    def test_git_is_preserved(self) -> None:
        """The self-workspace must stay a git checkout.

        ``workspace_git.py`` and the repo-status path both refuse a tree
        with no ``.git``, so excluding it would break the feature.
        """
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = self._make_seed(base)
            ws_base = base / "workspaces"
            ws_base.mkdir()
            target = ws_base / "u1" / "agentlayer-self"
            target.parent.mkdir(parents=True)

            self._copy_with_env(seed, target, ws_base)

            self.assertTrue((target / ".git" / "HEAD").exists())

    def test_missing_workspace_base_does_not_break_copy(self) -> None:
        """An unresolvable base must degrade to name-based ignoring, not raise."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = self._make_seed(base)
            target = base / "out" / "agentlayer-self"
            target.parent.mkdir(parents=True)

            # Base points at something that does not exist.
            self._copy_with_env(seed, target, base / "nope")

            self.assertTrue((target / "apps" / "main.py").exists())
            self.assertFalse((target / "node_modules").exists())


if __name__ == "__main__":
    unittest.main()
