"""The can_access adapter must load facts and route to the pure rules unchanged.

Uses a faked pool so the SQL result shape is the only thing under test — the
decision itself is covered in test_entity_access_rules.py.
"""

from __future__ import annotations

import uuid

import pytest

from apps.backend.infrastructure.access import entity_access_service as svc
from apps.backend.infrastructure.db import db

OWNER = uuid.uuid4()
OTHER = uuid.uuid4()
ENTITY = str(uuid.uuid4())


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def execute(self, *_a, **_k):
        return None

    def fetchone(self):
        return self._row

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, row):
        self._row = row

    def cursor(self):
        return _FakeCursor(self._row)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakePool:
    def __init__(self, row):
        self._row = row

    def connection(self):
        return _FakeConn(self._row)


def _patch(monkeypatch, row, tenant_id: int = 1):
    monkeypatch.setattr(db, "pool", lambda: _FakePool(row))
    monkeypatch.setattr(db, "user_tenant_id", lambda _uid: tenant_id)


# --------------------------------------------------------------------------
# Workspace routing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "owner, access_role, actor, needed, expected",
    [
        (OWNER, "owner", OWNER, "view", True),
        (OWNER, "owner", OWNER, "manage", True),
        (OWNER, "viewer", OWNER, "edit", False),
        (OWNER, "editor", OTHER, "view", True),
        (OWNER, "editor", OTHER, "edit", False),  # shared editor cannot edit
        (OWNER, "viewer", OTHER, "view", True),
        (OWNER, "viewer", OTHER, "manage", False),
    ],
)
def test_can_access_workspace(monkeypatch, owner, access_role, actor, needed, expected):
    _patch(monkeypatch, (owner, access_role))
    assert svc.can_access(svc.WORKSPACE, ENTITY, actor, needed) is expected


# --------------------------------------------------------------------------
# Dashboard routing
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "owner, member_role, actor, needed, expected",
    [
        (OWNER, None, OWNER, "manage", True),
        (OWNER, "viewer", OWNER, "manage", True),
        (OWNER, None, OTHER, "view", False),
        (OWNER, "co_owner", OTHER, "manage", True),
        (OWNER, "editor", OTHER, "edit", True),
        (OWNER, "editor", OTHER, "manage", False),
        (OWNER, "viewer", OTHER, "edit", False),
        (OWNER, "viewer", OTHER, "view", True),
    ],
)
def test_can_access_dashboard(monkeypatch, owner, member_role, actor, needed, expected):
    _patch(monkeypatch, (owner, member_role))
    assert svc.can_access(svc.DASHBOARD, ENTITY, actor, needed) is expected


# --------------------------------------------------------------------------
# Deny paths
# --------------------------------------------------------------------------


def test_missing_entity_denies(monkeypatch):
    _patch(monkeypatch, None)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view") is False
    assert svc.can_access(svc.DASHBOARD, ENTITY, OWNER, "view") is False


def test_unknown_entity_type_denies_without_query(monkeypatch):
    def _boom():
        raise AssertionError("must not hit the DB for an unsupported entity type")

    monkeypatch.setattr(db, "pool", _boom)
    assert svc.can_access("billing", ENTITY, OWNER, "view") is False


@pytest.mark.parametrize("actor", [None, "", object()])
def test_unresolvable_actor_denies_without_query(monkeypatch, actor):
    def _boom():
        raise AssertionError("must not hit the DB without a resolvable actor")

    monkeypatch.setattr(db, "pool", _boom)
    assert svc.can_access(svc.WORKSPACE, ENTITY, actor, "view") is False


def test_empty_entity_id_denies_without_query(monkeypatch):
    def _boom():
        raise AssertionError("must not hit the DB without an entity id")

    monkeypatch.setattr(db, "pool", _boom)
    assert svc.can_access(svc.WORKSPACE, "", OWNER, "view") is False


def test_actor_accepts_uuid_and_object_with_id(monkeypatch):
    _patch(monkeypatch, (OWNER, "owner"))

    class _Actor:
        id = OWNER

    class _StrIdActor:
        id = str(OWNER)

    assert svc.can_access(svc.WORKSPACE, ENTITY, _Actor(), "view") is True
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view") is True
    assert svc.can_access(svc.WORKSPACE, ENTITY, _StrIdActor(), "view") is True


def test_bare_string_actor_denies(monkeypatch):
    """A bare string is not an actor — it is ambiguous against the entity id."""

    def _boom():
        raise AssertionError("must not hit the DB for an unresolvable actor")

    monkeypatch.setattr(db, "pool", _boom)
    assert svc.can_access(svc.WORKSPACE, ENTITY, str(OWNER), "view") is False


def test_explicit_tenant_id_skips_the_tenant_lookup(monkeypatch):
    _patch(monkeypatch, (OWNER, "owner"))

    def _boom(_uid):
        raise AssertionError("must not resolve the actor tenant when one was passed")

    monkeypatch.setattr(db, "user_tenant_id", _boom)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view", tenant_id=7) is True


# --------------------------------------------------------------------------
# Row-based decision (no DB)
# --------------------------------------------------------------------------


def _ws_row(owner, access_role) -> tuple:
    """A project_workspaces row shaped by WORKSPACE_SELECT_SQL."""
    row = [None] * 28
    row[1] = owner
    row[7] = access_role
    row[27] = 1
    return tuple(row)


@pytest.mark.parametrize(
    "owner, access_role, actor, needed, expected",
    [
        (OWNER, "owner", OWNER, "owned", True),
        (OWNER, "owner", OWNER, "manage", True),
        (OWNER, "owner", OTHER, "owned", False),
        (OWNER, "editor", OTHER, "view", True),
        (OWNER, "editor", OTHER, "edit", False),
        (OWNER, "viewer", OTHER, "view", True),
        (OWNER, "viewer", OTHER, "owned", False),
    ],
)
def test_can_access_workspace_row(owner, access_role, actor, needed, expected):
    assert svc.can_access_workspace_row(_ws_row(owner, access_role), actor, needed) is expected


def test_can_access_workspace_row_denies_missing_row_or_actor():
    assert svc.can_access_workspace_row(None, OWNER, "view") is False
    assert svc.can_access_workspace_row(_ws_row(OWNER, "owner"), None, "view") is False


def test_can_access_workspace_row_makes_no_db_call(monkeypatch):
    def _boom():
        raise AssertionError("row-based decision must not touch the DB")

    monkeypatch.setattr(db, "pool", _boom)
    assert svc.can_access_workspace_row(_ws_row(OWNER, "owner"), OWNER, "manage") is True
