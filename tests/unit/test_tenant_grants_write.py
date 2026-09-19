"""Phase 5 — writing tenant grants without bridging two companies.

The reader keys grants on the entity's tenant, which makes a wrong-tenant row
inert. That does not stop a company B admin writing a row that names company
A's tenant, which would match A's members legitimately. These tests pin the
writer's refusal of a (entity, tenant) pair that does not agree.
"""

from __future__ import annotations

import uuid

import pytest

from apps.backend.infrastructure.access import tenant_grants as tg
from apps.backend.infrastructure.access.entity_access_service import DASHBOARD, WORKSPACE

WS_ID = str(uuid.uuid4())
DASH_ID = str(uuid.uuid4())
ACTOR = uuid.uuid4()


class _Cursor:
    def __init__(self, router, log):
        self._router = router
        self._log = log
        self._rows: list = []
        self.rowcount = 1

    def execute(self, sql, params=None):
        norm = " ".join(str(sql).split())
        self._log.append((norm, params))
        self._rows = list(self._router(norm, params))
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

    def connection(self):
        return self

    def cursor(self, **_kw):
        return _Cursor(self._router, self._log)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_exc):
        return False


def _patch(monkeypatch, router):
    log: list = []
    conn = _Conn(router, log)
    monkeypatch.setattr("apps.backend.infrastructure.db.db.pool", lambda: conn)
    return log, conn


def _is_write(sql: str) -> bool:
    return sql.startswith(("UPDATE ", "DELETE ", "INSERT "))


def _writes(log):
    return [s for s, _ in log if _is_write(s)]


def _router(ws_tenant=1, dash_tenant=1, grant_rows=()):
    """Answers entity-tenant lookups and grant reads; writes get no rows."""

    def route(sql, params):
        if _is_write(sql):
            return []
        if "SELECT tenant_id FROM project_workspaces WHERE id = %s" in sql:
            return [(ws_tenant,)] if ws_tenant is not None else []
        if "SELECT tenant_id FROM user_dashboards WHERE id = %s" in sql:
            return [(dash_tenant,)] if dash_tenant is not None else []
        if "FROM tenant_entity_grants" in sql:
            return list(grant_rows)
        raise AssertionError(f"unexpected SQL: {sql}")

    return route


# --------------------------------------------------------------------------
# entity_tenant
# --------------------------------------------------------------------------


def test_entity_tenant_reads_the_owning_tenant(monkeypatch):
    _patch(monkeypatch, _router(ws_tenant=42))
    assert tg.entity_tenant(WORKSPACE, WS_ID) == 42


def test_entity_tenant_is_none_when_the_entity_is_gone(monkeypatch):
    _patch(monkeypatch, _router(ws_tenant=None))
    assert tg.entity_tenant(WORKSPACE, WS_ID) is None


def test_entity_tenant_refuses_an_unknown_type(monkeypatch):
    _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError, match="unsupported entity type"):
        tg.entity_tenant("billing", WS_ID)


# --------------------------------------------------------------------------
# The cross-tenant lock
# --------------------------------------------------------------------------


def test_upsert_refuses_a_tenant_that_is_not_the_entitys(monkeypatch):
    """The attack: a grant naming a tenant the entity does not belong to."""
    log, conn = _patch(monkeypatch, _router(ws_tenant=1))
    with pytest.raises(tg.GrantError, match="belongs to tenant 1, not 2"):
        tg.upsert_grant(
            entity_type=WORKSPACE,
            entity_id=WS_ID,
            tenant_id=2,
            min_role="tenant_member",
            access="view",
            created_by=ACTOR,
        )
    assert _writes(log) == []
    assert conn.commits == 0


def test_upsert_refuses_a_dashboard_tenant_mismatch_too(monkeypatch):
    log, _conn = _patch(monkeypatch, _router(dash_tenant=7))
    with pytest.raises(tg.GrantError, match="belongs to tenant 7, not 8"):
        tg.upsert_grant(
            entity_type=DASHBOARD,
            entity_id=DASH_ID,
            tenant_id=8,
            min_role="tenant_member",
            access="view",
        )
    assert _writes(log) == []


def test_upsert_writes_when_the_tenant_agrees(monkeypatch):
    log, conn = _patch(monkeypatch, _router(ws_tenant=5))
    out = tg.upsert_grant(
        entity_type=WORKSPACE,
        entity_id=WS_ID,
        tenant_id=5,
        min_role="tenant_member",
        access="view",
        created_by=ACTOR,
    )
    assert out["tenant_id"] == 5
    assert out["min_role"] == "tenant_member"
    inserts = _writes(log)
    assert len(inserts) == 1
    assert inserts[0].startswith("INSERT INTO tenant_entity_grants")
    assert conn.commits == 1
    # created_by travels with the row
    assert ACTOR in (log[-1][1] or ())


def test_upsert_refuses_a_missing_entity(monkeypatch):
    log, _conn = _patch(monkeypatch, _router(ws_tenant=None))
    with pytest.raises(tg.GrantError, match="not found"):
        tg.upsert_grant(
            entity_type=WORKSPACE,
            entity_id=WS_ID,
            tenant_id=1,
            min_role="tenant_member",
            access="view",
        )
    assert _writes(log) == []


# --------------------------------------------------------------------------
# Shape validation
# --------------------------------------------------------------------------


def test_upsert_refuses_bad_min_role(monkeypatch):
    _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError, match="min_role must be one of"):
        tg.upsert_grant(
            entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=1,
            min_role="site_admin", access="view",
        )


def test_upsert_refuses_bad_access_level(monkeypatch):
    _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError, match="access must be one of"):
        tg.upsert_grant(
            entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=1,
            min_role="tenant_member", access="delete",
        )


def test_owned_is_not_grantable(monkeypatch):
    """``owned`` is pure ownership; the schema refuses it and so does the writer."""
    _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError, match="access must be one of"):
        tg.upsert_grant(
            entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=1,
            min_role="tenant_member", access="owned",
        )


def test_shape_is_checked_before_the_entity_is_touched(monkeypatch):
    """A bad role should fail without spending a query or writing anything."""
    log, _conn = _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError):
        tg.upsert_grant(
            entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=1,
            min_role="nope", access="view",
        )
    assert log == []


# --------------------------------------------------------------------------
# list / revoke
# --------------------------------------------------------------------------


def test_list_grants_shapes_rows(monkeypatch):
    _patch(
        monkeypatch,
        _router(grant_rows=[("tenant_member", "view", ACTOR, None)]),
    )
    got = tg.list_grants(WORKSPACE, WS_ID, 1)
    assert got == [
        {
            "min_role": "tenant_member",
            "access": "view",
            "created_by": str(ACTOR),
            "created_at": None,
        }
    ]


def test_revoke_targets_the_full_key(monkeypatch):
    log, conn = _patch(monkeypatch, _router())
    assert tg.revoke_grant(
        entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=3, min_role="tenant_member"
    ) is True
    sql, params = [w for w in log if w[0].startswith("DELETE")][0]
    assert "tenant_id = %s" in sql and "min_role = %s" in sql
    assert params == (WORKSPACE, WS_ID, 3, "tenant_member")
    assert conn.commits == 1


def test_revoke_refuses_an_unknown_min_role(monkeypatch):
    log, _conn = _patch(monkeypatch, _router())
    with pytest.raises(tg.GrantError, match="min_role must be one of"):
        tg.revoke_grant(
            entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=1, min_role="root"
        )
    assert _writes(log) == []


# --------------------------------------------------------------------------
# replace_grants
# --------------------------------------------------------------------------


def test_replace_clears_then_writes_the_stated_set(monkeypatch):
    log, conn = _patch(monkeypatch, _router(ws_tenant=9))
    out = tg.replace_grants(
        entity_type=WORKSPACE,
        entity_id=WS_ID,
        tenant_id=9,
        grants=[
            {"min_role": "tenant_member", "access": "view"},
            {"min_role": "tenant_admin", "access": "edit"},
        ],
        created_by=ACTOR,
    )
    assert len(out) == 2
    stmts = _writes(log)
    assert stmts[0].startswith("DELETE FROM tenant_entity_grants")
    assert sum(1 for s in stmts if s.startswith("INSERT")) == 2
    # one transaction: the whole set commits together
    assert conn.commits == 1


def test_replace_refuses_a_duplicate_min_role(monkeypatch):
    log, _conn = _patch(monkeypatch, _router(ws_tenant=9))
    with pytest.raises(tg.GrantError, match="appears more than once"):
        tg.replace_grants(
            entity_type=WORKSPACE,
            entity_id=WS_ID,
            tenant_id=9,
            grants=[
                {"min_role": "tenant_member", "access": "view"},
                {"min_role": "tenant_member", "access": "manage"},
            ],
        )
    assert _writes(log) == []


def test_replace_still_checks_the_tenant_before_clearing(monkeypatch):
    """A mismatched tenant must not even get as far as wiping existing grants."""
    log, _conn = _patch(monkeypatch, _router(ws_tenant=1))
    with pytest.raises(tg.GrantError, match="belongs to tenant 1, not 2"):
        tg.replace_grants(
            entity_type=WORKSPACE,
            entity_id=WS_ID,
            tenant_id=2,
            grants=[{"min_role": "tenant_member", "access": "view"}],
        )
    assert _writes(log) == []


def test_replace_with_an_empty_set_revokes_everything(monkeypatch):
    log, conn = _patch(monkeypatch, _router(ws_tenant=9))
    out = tg.replace_grants(
        entity_type=WORKSPACE, entity_id=WS_ID, tenant_id=9, grants=[]
    )
    assert out == []
    assert [s for s in _writes(log) if s.startswith("INSERT")] == []
    assert any(s.startswith("DELETE") for s in _writes(log))
    assert conn.commits == 1
