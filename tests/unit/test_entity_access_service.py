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


class _BoomPool:
    def __init__(self, why: str):
        self._why = why

    def connection(self):
        raise AssertionError(f"must not hit the DB: {self._why}")


class _FakeCursor:
    def __init__(self, router, calls):
        self._router = router
        self._calls = calls
        self._rows: list = []

    def execute(self, sql, params=()):
        self._calls.append((" ".join(str(sql).split()), params))
        self._rows = list(self._router(" ".join(str(sql).split()), params))
        return None

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeConn:
    def __init__(self, router, calls):
        self._router = router
        self._calls = calls

    def cursor(self):
        return _FakeCursor(self._router, self._calls)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakePool:
    def __init__(self, router, calls):
        self._router = router
        self._calls = calls

    def connection(self):
        return _FakeConn(self._router, self._calls)


def _router(entity_row=None, grant_rows=()):
    def route(sql, _params):
        if "FROM tenant_entity_grants" in sql:
            return list(grant_rows)
        if "FROM project_workspaces" in sql or "FROM user_dashboards" in sql:
            return [entity_row] if entity_row is not None else []
        raise AssertionError(f"unexpected SQL in test: {sql}")

    return route


def _patch(monkeypatch, row, tenant_id: int = 1, grant_rows=(), membership=None):
    calls: list = []
    monkeypatch.setattr(db, "pool", lambda: _FakePool(_router(row, grant_rows), calls))
    monkeypatch.setattr(db, "user_tenant_id", lambda _uid: tenant_id)
    monkeypatch.setattr(db, "user_membership_role", lambda _uid, _tid: membership)
    return calls


def _ws(owner, access_role, visibility="private", tenant_id=1):
    return (owner, access_role, visibility, tenant_id)


def _dash(owner, member_role, visibility="private", tenant_id=1):
    return (owner, member_role, visibility, tenant_id)


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
    _patch(monkeypatch, _ws(owner, access_role))
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
    _patch(monkeypatch, _dash(owner, member_role))
    assert svc.can_access(svc.DASHBOARD, ENTITY, actor, needed) is expected


# --------------------------------------------------------------------------
# Deny paths
# --------------------------------------------------------------------------


def test_missing_entity_denies(monkeypatch):
    _patch(monkeypatch, None)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view") is False
    assert svc.can_access(svc.DASHBOARD, ENTITY, OWNER, "view") is False


def test_unknown_entity_type_denies_without_query(monkeypatch):
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("unsupported entity type"))
    assert svc.can_access("billing", ENTITY, OWNER, "view") is False


@pytest.mark.parametrize("actor", [None, "", object()])
def test_unresolvable_actor_denies_without_query(monkeypatch, actor):
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("unresolvable actor"))
    assert svc.can_access(svc.WORKSPACE, ENTITY, actor, "view") is False


def test_empty_entity_id_denies_without_query(monkeypatch):
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("no entity id"))
    assert svc.can_access(svc.WORKSPACE, "", OWNER, "view") is False


def test_actor_accepts_uuid_and_object_with_id(monkeypatch):
    _patch(monkeypatch, _ws(OWNER, "owner"))

    class _Actor:
        id = OWNER

    class _StrIdActor:
        id = str(OWNER)

    assert svc.can_access(svc.WORKSPACE, ENTITY, _Actor(), "view") is True
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view") is True
    assert svc.can_access(svc.WORKSPACE, ENTITY, _StrIdActor(), "view") is True


def test_bare_string_actor_denies(monkeypatch):
    """A bare string is not an actor — it is ambiguous against the entity id."""
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("bare string actor"))
    assert svc.can_access(svc.WORKSPACE, ENTITY, str(OWNER), "view") is False


def test_explicit_tenant_id_skips_the_tenant_lookup(monkeypatch):
    _patch(monkeypatch, _ws(OWNER, "owner"))

    def _boom(_uid):
        raise AssertionError("must not resolve the actor tenant when one was passed")

    monkeypatch.setattr(db, "user_tenant_id", _boom)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "view", tenant_id=7) is True


# --------------------------------------------------------------------------
# Tenant layer — when it is and is not consulted
# --------------------------------------------------------------------------


def test_private_entity_never_consults_grants(monkeypatch):
    """A private entity is decided by the per-entity rule alone, so a stale grant
    row cannot reach it and the extra query is never made."""
    calls = _patch(
        monkeypatch,
        _ws(OWNER, "viewer", visibility="private"),
        grant_rows=[("tenant_member", "manage")],
        membership="tenant_admin",
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "edit") is False
    assert not [c for c in calls if "tenant_entity_grants" in c[0]]


def test_owner_never_consults_grants(monkeypatch):
    calls = _patch(
        monkeypatch,
        _ws(OWNER, "owner", visibility="tenant"),
        membership="tenant_member",
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OWNER, "manage") is True
    assert not [c for c in calls if "tenant_entity_grants" in c[0]]


def test_grants_consulted_only_after_per_entity_rule_denies(monkeypatch):
    calls = _patch(
        monkeypatch,
        _ws(OWNER, "viewer", visibility="tenant"),
        grant_rows=[("tenant_member", "edit")],
        membership="tenant_member",
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "edit") is True
    assert [c for c in calls if "tenant_entity_grants" in c[0]]


# --------------------------------------------------------------------------
# Tenant layer — the decided floor
# --------------------------------------------------------------------------


@pytest.mark.parametrize("needed", ["view", "edit", "manage"])
@pytest.mark.parametrize("role", ["tenant_admin", "tenant_owner"])
def test_tenant_admin_implicit_on_visible_workspace(monkeypatch, role, needed):
    # access_role=None so the per-entity rule denies and the tenant layer decides
    _patch(monkeypatch, _ws(OWNER, None, visibility="tenant"), membership=role)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, needed) is True


@pytest.mark.parametrize("needed", ["view", "edit", "manage"])
def test_tenant_member_needs_a_grant(monkeypatch, needed):
    _patch(monkeypatch, _ws(OWNER, None, visibility="tenant"), membership="tenant_member")
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, needed) is False


def test_tenant_member_with_view_grant_cannot_edit(monkeypatch):
    _patch(
        monkeypatch,
        _ws(OWNER, None, visibility="tenant"),
        grant_rows=[("tenant_member", "view")],
        membership="tenant_member",
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "view") is True
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "edit") is False


def test_no_membership_denies_even_with_a_grant(monkeypatch):
    """A grant row cannot pull in someone outside the tenant."""
    _patch(
        monkeypatch,
        _ws(OWNER, None, visibility="tenant"),
        grant_rows=[("tenant_member", "manage")],
        membership=None,
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "view") is False


@pytest.mark.parametrize("role", ["tenant_admin", "tenant_owner"])
def test_tenant_layer_never_satisfies_owned(monkeypatch, role):
    """owned is pure ownership; delegated authority must not impersonate it."""
    _patch(monkeypatch, _ws(OWNER, "owner", visibility="tenant"), membership=role)
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "owned") is False


def test_tenant_layer_works_for_dashboards_too(monkeypatch):
    _patch(
        monkeypatch,
        _dash(OWNER, None, visibility="tenant"),
        grant_rows=[("tenant_member", "edit")],
        membership="tenant_member",
    )
    assert svc.can_access(svc.DASHBOARD, ENTITY, OTHER, "edit") is True
    assert svc.can_access(svc.DASHBOARD, ENTITY, OTHER, "manage") is False


# --------------------------------------------------------------------------
# The cross-tenant invariant
# --------------------------------------------------------------------------


def test_grant_lookup_uses_the_entity_tenant_not_the_actors(monkeypatch):
    """The row's own tenant drives the grant lookup.

    Keying on the actor's tenant would let a company B admin write a grant
    naming a company A workspace and read it through their own tenant.
    """
    calls = _patch(
        monkeypatch,
        _ws(OWNER, None, visibility="tenant", tenant_id=42),
        tenant_id=1,  # the actor lives in tenant 1
        grant_rows=[("tenant_member", "view")],
        membership="tenant_member",
    )
    assert svc.can_access(svc.WORKSPACE, ENTITY, OTHER, "view") is True
    grant_calls = [c for c in calls if "tenant_entity_grants" in c[0]]
    assert grant_calls, "expected the grants table to be read"
    for _sql, params in grant_calls:
        assert 42 in params, "grant lookup must be keyed on the entity's tenant"
        assert 1 not in params, "grant lookup must not use the actor's tenant"


def test_tenant_layer_allows_rejects_unsupported_entity(monkeypatch):
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("unsupported entity type"))
    assert svc.tenant_layer_allows("billing", ENTITY, OTHER, 1, "view") is False


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
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("row-based decision"))
    assert svc.can_access_workspace_row(_ws_row(OWNER, "owner"), OWNER, "manage") is True


def test_can_access_workspace_row_composes_tenant_layer_without_io(monkeypatch):
    """A row alone cannot answer the tenant question, so the caller supplies it."""
    monkeypatch.setattr(db, "pool", lambda: _BoomPool("row-based decision"))
    row = _ws_row(OWNER, "viewer")
    assert svc.can_access_workspace_row(row, OTHER, "edit") is False
    assert svc.can_access_workspace_row(row, OTHER, "edit", tenant_allows=True) is True
