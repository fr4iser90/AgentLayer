"""The chat composer's workspace-preference guard must decide in the domain rule."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from apps.backend.infrastructure.platform.conversation_common import pref_workspace_allowed


def _call(row) -> tuple[bool, str, tuple]:
    cur = MagicMock()
    cur.fetchone.return_value = row
    ok = pref_workspace_allowed(cur, uuid.uuid4(), uuid.uuid4())
    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]
    return ok, " ".join(sql.split()), params


def test_owner_is_allowed() -> None:
    uid = uuid.uuid4()
    cur = MagicMock()
    cur.fetchone.return_value = (uid,)
    assert pref_workspace_allowed(cur, uid, uuid.uuid4()) is True


def test_non_owner_is_denied() -> None:
    uid = uuid.uuid4()
    cur = MagicMock()
    cur.fetchone.return_value = (uuid.uuid4(),)
    assert pref_workspace_allowed(cur, uid, uuid.uuid4()) is False


def test_missing_workspace_is_denied() -> None:
    ok, _, _ = _call(None)
    assert ok is False


def test_ownership_is_not_decided_in_sql() -> None:
    """The query fetches the owner; the rule decides.

    If the predicate crept back into the WHERE clause the guard would no longer be
    the shared one and a future tenant branch would silently skip it.
    """
    ok, sql, params = _call((uuid.uuid4(),))
    assert "owner_user_id" in sql
    assert "owner_user_id = %s" not in sql
    assert len(params) == 1


def test_null_owner_is_denied() -> None:
    uid = uuid.uuid4()
    cur = MagicMock()
    cur.fetchone.return_value = (None,)
    assert pref_workspace_allowed(cur, uid, uuid.uuid4()) is False
