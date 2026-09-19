"""A rejected create must never delete files it did not create.

The create path materialises the directory *before* the INSERT. When the INSERT
loses a unique constraint, the except-handler rmtree's the materialised
directory -- including the case where that directory already held an existing
workspace's files.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from psycopg import errors as pg_errors

from apps.backend.infrastructure.workspace import workspace_project_service as svc

OWNER = uuid.uuid4()


class _Cursor:
    def __init__(self, log):
        self._log = log
        self._last = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        s = " ".join(str(sql).split())
        self._last = s
        self._log.append(s)
        if s.startswith("INSERT"):
            raise pg_errors.UniqueViolation()
        return None

    def fetchone(self):
        # Generous quota, nothing created yet: the guards must let the create reach
        # the disk, where the collision actually bites.
        if "COALESCE(workspace_quota" in self._last:
            return (99,)
        return (0,)

    def fetchall(self):
        return []


class _Conn:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def connection(self):
        return self

    def cursor(self, **_kw):
        return _Cursor(self._log)

    def commit(self):
        pass


def _run(monkeypatch, tmp_path: Path, *, name: str):
    log: list = []
    base = tmp_path / "wsbase"

    monkeypatch.setattr(svc, "_workspace_base_path", lambda: base)
    monkeypatch.setattr("apps.backend.infrastructure.db.db.pool", lambda: _Conn(log))
    monkeypatch.setattr("apps.backend.infrastructure.db.db.user_tenant_id", lambda _u: 1)
    monkeypatch.setattr(
        "apps.backend.domain.shared.identity.get_benchmark_run_id", lambda: None
    )
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_api_key_workspace_mode",
        lambda _m: None,
    )
    monkeypatch.setattr(
        "apps.backend.infrastructure.platform.client_surface_policy"
        ".refuse_server_workspace_for_user",
        lambda _u, _m: None,
    )
    user = SimpleNamespace(id=OWNER, role="user")
    with pytest.raises(svc.WorkspaceCreateError):
        svc.create_project_workspace_for_user(
            user, name=name, source="manual", execution_mode="server"
        )
    return base


def test_rejected_duplicate_does_not_wipe_the_existing_workspace(monkeypatch, tmp_path):
    """Pre-existing files under the colliding path must survive the failed create."""
    base = tmp_path / "wsbase"
    prior = base / str(OWNER) / "repo"
    prior.mkdir(parents=True, exist_ok=True)
    (prior / "precious.txt").write_text("do not delete me\n")

    _run(monkeypatch, tmp_path, name="repo")

    assert (prior / "precious.txt").exists(), (
        "the failed create deleted files belonging to an existing workspace"
    )
