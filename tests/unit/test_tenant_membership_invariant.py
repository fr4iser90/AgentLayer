"""The ghost-membership invariant and the tenant move that keeps it intact.

``require_tenant_member`` reads ``tenant_memberships``; ``resolve_chat_identity``
reads ``users.tenant_id``. If the two disagree the user can enter a tenant but
every write still lands in their home tenant, silently. These tests pin the two
write paths down so they cannot diverge.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest

from apps.backend.infrastructure.db import identity_tenants as it
from apps.backend.infrastructure.identity import auth as auth_mod

USER = uuid.uuid4()


class _Cursor:
    def __init__(self, script: list, log: list) -> None:
        self._script = list(script)
        self._log = log
        self.rowcount = 1

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self._log.append((" ".join(str(sql).split()), params))

    def fetchone(self):
        return self._script.pop(0) if self._script else None


class _Conn:
    def __init__(self, script: list, log: list) -> None:
        self._cursor = _Cursor(script, log)
        self.commits = 0

    def __enter__(self) -> "_Conn":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def connection(self) -> "_Conn":
        return self

    def cursor(self, **_kw: object) -> _Cursor:
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


def _fake_pool(script: list) -> tuple[list, _Conn]:
    log: list = []
    return log, _Conn(script, log)


def _sql_containing(log: list, needle: str) -> list[str]:
    return [sql for sql, _ in log if needle in sql]


def _params_for(log: list, needle: str) -> list[object]:
    return [params for sql, params in log if needle in sql]


# --- tenant_membership_upsert ---


def test_membership_upsert_rejects_unknown_user() -> None:
    log, conn = _fake_pool([None])
    with patch.object(it, "pool", lambda: conn):
        with pytest.raises(ValueError, match="unknown user"):
            it.tenant_membership_upsert(USER, 1, "tenant_member")
    assert _sql_containing(log, "INSERT") == []
    assert conn.commits == 0


def test_membership_upsert_rejects_ghost_membership() -> None:
    """Home tenant 1, membership written for tenant 2 — the ghost."""
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        with pytest.raises(ValueError, match="not the home tenant"):
            it.tenant_membership_upsert(USER, 2, "tenant_admin")
    assert _sql_containing(log, "INSERT") == []
    assert conn.commits == 0


def test_membership_upsert_allows_home_tenant() -> None:
    log, conn = _fake_pool([(2,)])
    with patch.object(it, "pool", lambda: conn):
        it.tenant_membership_upsert(USER, 2, "tenant_admin")
    inserts = _sql_containing(log, "INSERT INTO tenant_memberships")
    assert len(inserts) == 1
    assert log[-1][1] == (USER, 2, "tenant_admin")
    assert conn.commits == 1


def test_membership_upsert_normalises_unknown_role() -> None:
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        it.tenant_membership_upsert(USER, 1, "supreme_leader")
    assert log[-1][1] == (USER, 1, "tenant_member")


# --- move_user_tenant ---


def test_move_unknown_user_returns_false() -> None:
    log, conn = _fake_pool([None])
    with patch.object(it, "pool", lambda: conn):
        assert it.move_user_tenant(USER, 2) is False
    assert _sql_containing(log, "UPDATE users") == []


def test_move_to_same_tenant_leaves_memberships_alone() -> None:
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        assert it.move_user_tenant(USER, 1) is True
    assert _sql_containing(log, "UPDATE users SET tenant_id") == ["UPDATE users SET tenant_id = %s WHERE id = %s"]
    assert _sql_containing(log, "tenant_memberships") == []


def test_move_carries_the_membership_row() -> None:
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        assert it.move_user_tenant(USER, 2) is True
    assert len(_sql_containing(log, "DELETE FROM tenant_memberships")) == 1
    assert len(_sql_containing(log, "INSERT INTO tenant_memberships")) == 1
    assert _params_for(log, "INSERT INTO tenant_memberships") == [(USER, 2, "tenant_member")]
    assert conn.commits == 1


def test_move_never_carries_owner_rights_into_the_new_tenant() -> None:
    """The old role is not even read, so tenant_owner cannot follow the person."""
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        it.move_user_tenant(USER, 2)
    assert _sql_containing(log, "SELECT membership_role") == []
    assert _params_for(log, "INSERT INTO tenant_memberships") == [(USER, 2, "tenant_member")]


def test_move_clears_memberships_in_every_other_tenant() -> None:
    """No stale rows left behind in tenants the person used to belong to."""
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        it.move_user_tenant(USER, 4)
    deletes = _sql_containing(log, "DELETE FROM tenant_memberships")
    assert deletes == ["DELETE FROM tenant_memberships WHERE user_id = %s AND tenant_id <> %s"]
    assert _params_for(log, "DELETE FROM tenant_memberships") == [(USER, 4)]


def test_move_takes_owned_workspaces_along() -> None:
    """project_workspaces.tenant_id is denormalised from the owner, so a move
    that left it behind would make every later workspace scope check wrong."""
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        it.move_user_tenant(USER, 7)
    assert _params_for(log, "UPDATE project_workspaces SET tenant_id") == [(7, USER)]


def test_same_tenant_move_touches_no_workspaces() -> None:
    log, conn = _fake_pool([(1,)])
    with patch.object(it, "pool", lambda: conn):
        it.move_user_tenant(USER, 1)
    assert _sql_containing(log, "UPDATE project_workspaces") == []


def test_auth_update_user_tenant_goes_through_the_guarded_move() -> None:
    """``auth.update_user_tenant`` must not call the bare primitive again — that
    is the one that would drag tenant-visible entities into the new tenant."""
    calls: list[tuple] = []
    with (
        patch.object(
            auth_mod,
            "guarded_move_user_tenant",
            side_effect=lambda u, t: calls.append((u, t)) or True,
        ),
    ):
        assert auth_mod.update_user_tenant(USER, 5) is True
    assert calls == [(USER, 5)]
