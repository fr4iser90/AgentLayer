"""Phase 5 — the ``scope=company`` workspace list and the visibility mapping.

Two things matter here and neither is obvious from the happy path:

* the company query filters on **both** ``tenant_id`` and ``visibility``. Drop
  the visibility predicate and a member sees every workspace in their tenant,
  including private ones; drop the tenant predicate and they see other companies'
  shared workspaces. A test that only checks "rows came back" sees neither.
* the tenant is read from the caller's membership, never from the request, and a
  caller with no tenant must not reach the query at all.

The SELECT-list position test guards the index constants: ``WORKSPACE_SELECT_SQL``
is consumed positionally, so inserting a column without moving
``TENANT_ID_INDEX`` / ``VISIBILITY_INDEX`` would silently relabel every row.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.backend.api.workspaces.controllers import workspaces_api as api
from apps.backend.application.workspace.use_cases import workspace_controller_services as ws_services
from apps.backend.infrastructure.workspace.workspace_columns import (
    TENANT_ID_INDEX,
    VISIBILITY_INDEX,
    WORKSPACE_SELECT_SQL,
    _visibility_from_row,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeCur:
    def __init__(self, calls, rows):
        self._calls = calls
        self._rows = rows

    def execute(self, sql, params=None):
        self._calls.append((sql, params))

    def fetchall(self):
        return self._rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, cur):
        self._conn = _FakeConn(cur)

    def connection(self):
        return self._conn


def _query_company(tenant_id, rows=()):
    calls = []
    cur = _FakeCur(calls, list(rows))
    with patch.object(ws_services.db, "pool", return_value=_FakePool(cur)):
        out = ws_services.fetch_company_workspace_rows(tenant_id)
    return out, calls


# --------------------------------------------------------------------------
# The company query
# --------------------------------------------------------------------------


def test_company_query_filters_on_tenant_and_visibility():
    _, calls = _query_company(7, rows=[("r",)])
    assert len(calls) == 1
    sql, params = calls[0]
    assert "tenant_id = %s" in sql
    assert "visibility = 'tenant'" in sql
    assert params == (7,)


def test_company_query_is_one_statement_carrying_both_predicates():
    """Counterpart to the above: the predicates must not be split across queries."""
    _, calls = _query_company(7)
    assert len(calls) == 1
    sql, _ = calls[0]
    where = sql.upper().split("WHERE", 1)[1]
    assert "TENANT_ID = %S" in where
    assert "VISIBILITY = 'TENANT'" in where


def test_company_query_coerces_a_string_tenant_to_int():
    """A bigint arriving as ``'7'`` must not become a different filter value."""
    _, calls = _query_company("7")
    assert calls[0][1] == (7,)


def test_company_query_returns_what_the_db_gave():
    rows = [("a",), ("b",)]
    out, _ = _query_company(1, rows=rows)
    assert out == rows


# --------------------------------------------------------------------------
# The controller's tenant resolution
# --------------------------------------------------------------------------


def _caller(tenant_id):
    user = MagicMock()
    user.id = uuid.uuid4()
    return user


def test_company_scope_asks_about_the_callers_tenant():
    user = _caller(3)
    with patch.object(api, "get_current_user", AsyncMock(return_value=user)), patch.object(
        api.ws_services.db, "user_tenant_id", return_value=3
    ) as resolve, patch.object(
        api.ws_services, "fetch_company_workspace_rows", return_value=[("r",)]
    ) as fetch, patch.object(api, "_row_to_workspace", side_effect=lambda r: {"name": "r"}):
        out = _run(api.list_workspaces(MagicMock(), scope="company"))

    resolve.assert_called_once_with(user.id)
    fetch.assert_called_once_with(3)
    assert out["scope"] == "company"
    assert out["tenant_id"] == 3
    assert len(out["workspaces"]) == 1


def test_caller_without_a_tenant_never_reaches_the_query():
    user = _caller(None)
    with patch.object(api, "get_current_user", AsyncMock(return_value=user)), patch.object(
        api.ws_services.db, "user_tenant_id", return_value=None
    ), patch.object(api.ws_services, "fetch_company_workspace_rows") as fetch:
        out = _run(api.list_workspaces(MagicMock(), scope="company"))

    fetch.assert_not_called()
    assert out == {"workspaces": [], "scope": "company", "tenant_id": None}


def test_scope_is_case_and_whitespace_insensitive():
    user = _caller(2)
    with patch.object(api, "get_current_user", AsyncMock(return_value=user)), patch.object(
        api.ws_services.db, "user_tenant_id", return_value=2
    ), patch.object(api.ws_services, "fetch_company_workspace_rows", return_value=[]) as fetch:
        out = _run(api.list_workspaces(MagicMock(), scope="  Company "))
    fetch.assert_called_once_with(2)
    assert out["scope"] == "company"


def test_an_unknown_scope_falls_back_to_mine():
    user = _caller(2)
    with patch.object(api, "get_current_user", AsyncMock(return_value=user)), patch.object(
        api.ws_services, "fetch_owned_workspace_rows", return_value=[]
    ) as mine, patch.object(api.ws_services, "self_editing_allowed", return_value=False), patch.object(
        api, "_get_self_workspace", return_value=None
    ), patch.object(api.ws_services, "fetch_company_workspace_rows") as company:
        out = _run(api.list_workspaces(MagicMock(), scope="everybody"))

    company.assert_not_called()
    mine.assert_called_once_with(user.id)
    assert out["scope"] == "mine"


def test_mine_scope_still_hides_the_self_workspace_when_self_editing_is_off():
    user = _caller(2)
    self_name = ws_services.AGENTLAYER_SELF_NAME
    rows = [("own",), (self_name,)]
    with patch.object(api, "get_current_user", AsyncMock(return_value=user)), patch.object(
        api.ws_services, "fetch_owned_workspace_rows", return_value=rows
    ), patch.object(api.ws_services, "self_editing_allowed", return_value=False), patch.object(
        api, "_get_self_workspace", return_value=None
    ), patch.object(
        api, "_row_to_workspace", side_effect=lambda r: {"name": r[0]}
    ):
        out = _run(api.list_workspaces(MagicMock(), scope="mine"))

    names = [w["name"] for w in out["workspaces"]]
    assert names == ["own"]


# --------------------------------------------------------------------------
# The visibility mapping
# --------------------------------------------------------------------------


def test_select_list_position_matches_the_index_constants():
    cols = [c.strip() for c in WORKSPACE_SELECT_SQL.replace("\n", " ").split(",")]
    assert cols[TENANT_ID_INDEX] == "tenant_id"
    assert cols[VISIBILITY_INDEX] == "visibility"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("tenant", "tenant"),
        ("TENANT", "tenant"),
        ("  tenant  ", "tenant"),
        ("private", "private"),
        ("Public", "private"),
        ("", "private"),
        (None, "private"),
    ],
)
def test_only_the_tenant_value_reads_as_company(raw, expected):
    row = tuple([None] * VISIBILITY_INDEX + [raw])
    assert _visibility_from_row(row) == expected


def test_a_row_shorter_than_the_visibility_column_reads_private():
    """A SELECT that predates the column must not surface as company-visible."""
    assert _visibility_from_row(tuple([None] * VISIBILITY_INDEX)) == "private"
