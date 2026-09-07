from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path


class _FakeCursor:
    def __init__(self, expected_path: str, wid: str):
        self._expected_path = expected_path
        self._wid = wid
        self._last_query = ""
        self._last_params = ()

    def execute(self, query: str, params=()):
        self._last_query = query
        self._last_params = params

    def fetchone(self):
        q = self._last_query.lower()
        # SELECT id, path ...
        if "select id, path from project_workspaces" in q:
            return (self._wid, self._expected_path)
        # INSERT ... RETURNING id
        if "returning id" in q:
            return (self._wid,)
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, expected_path: str, wid: str):
        self._expected_path = expected_path
        self._wid = wid

    def cursor(self):
        return _FakeCursor(self._expected_path, self._wid)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, expected_path: str, wid: str):
        self._expected_path = expected_path
        self._wid = wid

    def connection(self):
        return _FakeConn(self._expected_path, self._wid)


class _User:
    def __init__(self, uid: str):
        self.id = uid
        self.role = "admin"


class TestSelfWorkspaceReset(unittest.TestCase):
    def test_reset_with_backup_moves_old_tree(self) -> None:
        from apps.backend.infrastructure.workspace import workspace_service as ws

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = base / "seed"
            target = base / "target" / "agentlayer-self"
            target.parent.mkdir(parents=True, exist_ok=True)

            # Create seed repo layout
            (seed / ".git").mkdir(parents=True, exist_ok=True)
            (seed / "seed.txt").write_text("seed", encoding="utf-8")

            # Create existing target contents
            target.mkdir(parents=True, exist_ok=True)
            (target / "old.txt").write_text("old", encoding="utf-8")

            user = _User(uid=str(uuid.uuid4()))
            wid = str(uuid.uuid4())
            expected_path = str(target)

            # Patch hooks for deterministic filesystem + DB interactions.
            old_allowed = ws.self_editing_allowed
            old_seed = ws._agentlayer_self_seed_dir
            old_target = ws.self_workspace_target_path

            import apps.backend.infrastructure.db.db as db_mod
            import apps.backend.domain.workspace.resolver as resolver_mod

            old_pool_fn = db_mod.pool
            old_resolve = resolver_mod.resolve_db_workspace

            try:
                ws.self_editing_allowed = lambda _u: True
                ws._agentlayer_self_seed_dir = lambda: seed
                ws.self_workspace_target_path = lambda _u: target
                fake_pool = _FakePool(expected_path=expected_path, wid=wid)
                db_mod.pool = lambda: fake_pool
                resolver_mod.resolve_db_workspace = lambda _wid, _u: {"id": _wid, "path": expected_path}

                out = ws.reset_agentlayer_self_workspace(user, backup_existing=True)
                self.assertIsNotNone(out)
                self.assertTrue((target / "seed.txt").exists())
                self.assertFalse((target / "old.txt").exists())

                # Backup dir should exist with old file.
                backups = sorted(target.parent.glob("agentlayer-self.backup-*"))
                self.assertEqual(len(backups), 1)
                self.assertTrue((backups[0] / "old.txt").exists())
            finally:
                ws.self_editing_allowed = old_allowed
                ws._agentlayer_self_seed_dir = old_seed
                ws.self_workspace_target_path = old_target
                db_mod.pool = old_pool_fn
                resolver_mod.resolve_db_workspace = old_resolve

    def test_reset_without_backup_deletes_old_tree(self) -> None:
        from apps.backend.infrastructure.workspace import workspace_service as ws

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            seed = base / "seed"
            target = base / "target" / "agentlayer-self"
            target.parent.mkdir(parents=True, exist_ok=True)

            (seed / ".git").mkdir(parents=True, exist_ok=True)
            (seed / "seed.txt").write_text("seed", encoding="utf-8")

            target.mkdir(parents=True, exist_ok=True)
            (target / "old.txt").write_text("old", encoding="utf-8")

            user = _User(uid=str(uuid.uuid4()))
            wid = str(uuid.uuid4())
            expected_path = str(target)

            old_allowed = ws.self_editing_allowed
            old_seed = ws._agentlayer_self_seed_dir
            old_target = ws.self_workspace_target_path

            import apps.backend.infrastructure.db.db as db_mod
            import apps.backend.domain.workspace.resolver as resolver_mod

            old_pool_fn = db_mod.pool
            old_resolve = resolver_mod.resolve_db_workspace

            try:
                ws.self_editing_allowed = lambda _u: True
                ws._agentlayer_self_seed_dir = lambda: seed
                ws.self_workspace_target_path = lambda _u: target
                fake_pool = _FakePool(expected_path=expected_path, wid=wid)
                db_mod.pool = lambda: fake_pool
                resolver_mod.resolve_db_workspace = lambda _wid, _u: {"id": _wid, "path": expected_path}

                out = ws.reset_agentlayer_self_workspace(user, backup_existing=False)
                self.assertIsNotNone(out)
                self.assertTrue((target / "seed.txt").exists())
                self.assertFalse((target / "old.txt").exists())
                backups = sorted(target.parent.glob("agentlayer-self.backup-*"))
                self.assertEqual(backups, [])
            finally:
                ws.self_editing_allowed = old_allowed
                ws._agentlayer_self_seed_dir = old_seed
                ws.self_workspace_target_path = old_target
                db_mod.pool = old_pool_fn
                resolver_mod.resolve_db_workspace = old_resolve


if __name__ == "__main__":
    unittest.main()

