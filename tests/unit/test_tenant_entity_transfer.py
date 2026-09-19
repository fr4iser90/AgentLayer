"""Phase 3 — a tenant move must not drag company data along with the person.

Covers the guard on ``move_user_tenant`` and the transfer that unblocks it.
"""

from __future__ import annotations

import uuid

import pytest

from apps.backend.domain.access.tenant_ownership import (
    TenantOwnedEntitiesConflict,
    same_tenant,
)
from apps.backend.infrastructure.access import entity_access_service as svc
from apps.backend.infrastructure.access import tenant_entity_transfer as xfer
from apps.backend.infrastructure.db import identity_tenants as it

OWNER = uuid.uuid4()
TARGET = uuid.uuid4()
ENTITY = str(uuid.uuid4())


class _Cursor:
    def __init__(self, router, log):
        self._router = router
        self._log = log
        self._rows: list = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        norm = " ".join(str(sql).split())
        self._log.append((norm, params))
        self._rows = list(self._router(norm))
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _Conn:
    def __init__(self, router, log):
        self._router = router
        self._log = log
        self.commits = 0
        self.rolled_back = False

    def connection(self):
        return self

    def cursor(self, **_kw):
        return _Cursor(self._router, self._log)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_exc):
        if exc_type is not None:
            self.rolled_back = True
        return False


def _patch(monkeypatch, router):
    log: list = []
    conn = _Conn(router, log)
    monkeypatch.setattr(it, "pool", lambda: conn)
    monkeypatch.setattr("apps.backend.infrastructure.db.db.pool", lambda: conn)
    return log, conn


def _ws_entity(tenant=1, owner=OWNER, name="repo", visibility="tenant"):
    return (uuid.uuid4(), tenant, owner, name, visibility)


def _dash_entity(tenant=1, owner=OWNER, title="Ops", visibility="tenant"):
    return (uuid.uuid4(), tenant, owner, title, visibility)


def _is_write(sql: str) -> bool:
    """Writes get no result rows; the router only supplies SELECT answers."""
    return sql.startswith(("UPDATE ", "DELETE ", "INSERT "))


def _router(entity=None, target=(1,), counts=(0, 0), name_taken=False):
    def route(sql):
        if _is_write(sql):
            return []
        if "COUNT(*) FROM project_workspaces" in sql:
            return [counts]
        if "SELECT 1 FROM project_workspaces WHERE owner_user_id = %s AND name = %s" in sql:
            return [(1,)] if name_taken else []
        if "FROM users WHERE id = %s" in sql:
            return [target] if target else []
        if "FROM project_workspaces WHERE id = %s" in sql:
            return [entity] if entity is not None else []
        if "FROM user_dashboards WHERE id = %s" in sql:
            return [entity] if entity is not None else []
        raise AssertionError(f"unexpected SQL: {sql}")

    return route


# --------------------------------------------------------------------------
# same_tenant
# --------------------------------------------------------------------------


def test_same_tenant_matches_only_equal_known_tenants():
    assert same_tenant(1, 1) is True
    assert same_tenant(1, 2) is False
    assert same_tenant(None, 1) is False
    assert same_tenant(1, None) is False
    assert same_tenant("3", 3) is True  # bigint arrives as str sometimes


# --------------------------------------------------------------------------
# The move guard
# --------------------------------------------------------------------------


def test_move_allowed_when_nothing_is_tenant_visible(monkeypatch):
    log, conn = _patch(monkeypatch, _router(counts=(0, 0)))
    assert xfer.guarded_move_user_tenant(OWNER, 2) is True
    assert conn.commits >= 1


def test_move_blocked_when_user_owns_tenant_visible_workspace(monkeypatch):
    log, conn = _patch(monkeypatch, _router(counts=(2, 0)))
    with pytest.raises(TenantOwnedEntitiesConflict) as exc:
        xfer.guarded_move_user_tenant(OWNER, 2)
    assert exc.value.workspace_count == 2
    assert exc.value.dashboard_count == 0
    assert exc.value.total == 2
    assert_writes(log, [])


def test_move_blocked_by_a_single_tenant_visible_dashboard(monkeypatch):
    log, conn = _patch(monkeypatch, _router(counts=(0, 1)))
    with pytest.raises(TenantOwnedEntitiesConflict):
        xfer.guarded_move_user_tenant(OWNER, 3)
    assert_writes(log, [])


def test_same_tenant_move_is_not_blocked(monkeypatch):
    """Not a move at all — the guard only fires on an actual tenant change."""
    log, conn = _patch(monkeypatch, _router(counts=(5, 5)))
    assert xfer.guarded_move_user_tenant(OWNER, 1) is True
    assert _sql(log, "COUNT(*) FROM project_workspaces") == []


def test_bare_db_move_is_the_unguarded_primitive(monkeypatch):
    """Documented consequence of keeping the policy out of the plumbing: the
    primitive itself does not refuse. Callers must use the guarded entry."""
    log, conn = _patch(monkeypatch, _router(counts=(4, 4)))
    assert it.move_user_tenant(OWNER, 2) is True
    assert _sql(log, "COUNT(*) FROM project_workspaces") == []


def test_unknown_user_still_returns_false_not_raises(monkeypatch):
    log, conn = _patch(monkeypatch, _router(counts=(9, 9)))
    # no user row -> early False, before any guard
    def route(sql):
        if "SELECT tenant_id FROM users WHERE id = %s" in sql:
            return []
        raise AssertionError(f"should not get this far: {sql}")

    log, conn = _patch(monkeypatch, route)
    assert it.move_user_tenant(OWNER, 2) is False


def _sql(log, needle):
    return [s for s, _ in log if needle in s]


def assert_writes(log, expected):
    """The write statements actually issued.

    A refusal must be shown to have written nothing. A read-only commit from a
    tenant lookup is not a write, so counting commits would be the wrong check.
    """
    writes = [s for s, _ in log if _is_write(s)]
    assert writes == list(expected), f"unexpected writes: {writes}"


# --------------------------------------------------------------------------
# count_tenant_owned_entities
# --------------------------------------------------------------------------


def test_count_returns_both_sides(monkeypatch):
    _patch(monkeypatch, _router(counts=(3, 4)))
    assert xfer.count_tenant_owned_entities(OWNER) == (3, 4)


def test_count_is_zero_when_nothing_matches(monkeypatch):
    _patch(monkeypatch, _router(counts=(0, 0)))
    assert xfer.count_tenant_owned_entities(OWNER) == (0, 0)


# --------------------------------------------------------------------------
# transfer_entity_ownership — workspace
# --------------------------------------------------------------------------


def test_transfer_workspace_within_tenant(monkeypatch):
    ent = _ws_entity(tenant=7)
    log, conn = _patch(monkeypatch, _router(entity=ent, target=(7,)))
    out = xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)
    assert out["tenant_id"] == 7
    assert out["new_owner"] == str(TARGET)
    assert out["previous_owner"] == str(OWNER)
    upd = _sql(log, "UPDATE project_workspaces SET owner_user_id")
    assert len(upd) == 1
    assert "access_role = 'owner'" in upd[0]
    assert conn.commits == 1


def test_transfer_refuses_cross_tenant_target(monkeypatch):
    ent = _ws_entity(tenant=7)
    log, conn = _patch(monkeypatch, _router(entity=ent, target=(8,)))
    with pytest.raises(xfer.TransferError, match="tenant 8"):
        xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)
    assert _sql(log, "UPDATE project_workspaces") == []
    assert conn.commits == 0


def test_transfer_refuses_missing_entity(monkeypatch):
    _patch(monkeypatch, _router(entity=None, target=(1,)))
    with pytest.raises(xfer.TransferError, match="not found"):
        xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)


def test_transfer_refuses_missing_target_user(monkeypatch):
    ent = _ws_entity()
    _patch(monkeypatch, _router(entity=ent, target=None))
    with pytest.raises(xfer.TransferError, match="target user not found"):
        xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)


def test_transfer_refuses_target_who_already_owns_it(monkeypatch):
    ent = _ws_entity(tenant=1, owner=TARGET)
    _patch(monkeypatch, _router(entity=ent, target=(1,)))
    with pytest.raises(xfer.TransferError, match="already owns"):
        xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)


def test_transfer_refuses_workspace_name_collision(monkeypatch):
    ent = _ws_entity(tenant=1, name="shared-repo")
    log, conn = _patch(monkeypatch, _router(entity=ent, target=(1,), name_taken=True))
    with pytest.raises(xfer.TransferError, match="shared-repo"):
        xfer.transfer_entity_ownership(svc.WORKSPACE, ENTITY, TARGET)
    assert _sql(log, "UPDATE project_workspaces") == []
    assert conn.commits == 0


def test_transfer_rejects_unknown_entity_type(monkeypatch):
    _patch(monkeypatch, _router())
    with pytest.raises(xfer.TransferError, match="unsupported entity type"):
        xfer.transfer_entity_ownership("billing", ENTITY, TARGET)


# --------------------------------------------------------------------------
# transfer_entity_ownership — dashboard
# --------------------------------------------------------------------------


def test_transfer_dashboard_within_tenant(monkeypatch):
    ent = _dash_entity(tenant=4)
    log, conn = _patch(monkeypatch, _router(entity=ent, target=(4,)))
    out = xfer.transfer_entity_ownership(svc.DASHBOARD, ENTITY, TARGET)
    assert out["tenant_id"] == 4
    assert out["visibility"] == "tenant"
    assert len(_sql(log, "UPDATE user_dashboards SET owner_user_id")) == 1
    # dashboards have no per-owner unique title, so no collision probe
    assert _sql(log, "SELECT 1 FROM project_workspaces") == []
    assert conn.commits == 1


def test_transfer_dashboard_refuses_cross_tenant(monkeypatch):
    ent = _dash_entity(tenant=4)
    log, conn = _patch(monkeypatch, _router(entity=ent, target=(5,)))
    with pytest.raises(xfer.TransferError):
        xfer.transfer_entity_ownership(svc.DASHBOARD, ENTITY, TARGET)
    assert _sql(log, "UPDATE user_dashboards") == []


# --------------------------------------------------------------------------
# transfer_all_tenant_entities
# --------------------------------------------------------------------------


def test_transfer_all_moves_every_visible_entity(monkeypatch):
    ws_id = str(uuid.uuid4())
    dash_id = str(uuid.uuid4())

    def route(sql):
        if _is_write(sql):
            return []
        if "FROM project_workspaces" in sql and "visibility = 'tenant'" in sql and "COUNT" not in sql:
            return [("workspace", ws_id)]
        if "FROM user_dashboards" in sql and "visibility = 'tenant'" in sql:
            return [("dashboard", dash_id)]
        if "name, visibility FROM project_workspaces WHERE id = %s" in sql:
            return [_ws_entity(tenant=2, owner=OWNER)]
        if "title, visibility FROM user_dashboards WHERE id = %s" in sql:
            return [_dash_entity(tenant=2, owner=OWNER)]
        if "FROM users WHERE id = %s" in sql:
            return [(2,)]
        if "SELECT 1 FROM project_workspaces WHERE owner_user_id = %s AND name = %s" in sql:
            return []
        raise AssertionError(f"unexpected SQL: {sql}")

    log, conn = _patch(monkeypatch, route)
    moved = xfer.transfer_all_tenant_entities(OWNER, TARGET)
    assert len(moved) == 2
    assert {m["entity_type"] for m in moved} == {"workspace", "dashboard"}
    assert all(m["new_owner"] == str(TARGET) for m in moved)


def test_transfer_all_is_empty_when_nothing_is_visible(monkeypatch):
    def route(sql):
        if _is_write(sql):
            return []
        if "COUNT(*) FROM project_workspaces" in sql:
            return [(0, 0)]
        if "FROM project_workspaces" in sql or "FROM user_dashboards" in sql:
            return []
        if "FROM users WHERE id = %s" in sql:
            return [(1,)]
        raise AssertionError(sql)

    _patch(monkeypatch, route)
    assert xfer.transfer_all_tenant_entities(OWNER, TARGET) == []
