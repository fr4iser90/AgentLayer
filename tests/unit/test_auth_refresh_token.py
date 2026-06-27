"""Unit tests for refresh token hashing and lookup."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.identity import auth as mod


def test_hash_refresh_token_is_sha256_hex() -> None:
    h = mod.hash_refresh_token("abc")
    assert len(h) == 64
    assert h == mod.hash_refresh_token("abc")
    assert h != mod.hash_refresh_token("abd")


def test_validate_refresh_token_uses_index_lookup() -> None:
    user_id = uuid.uuid4()
    raw = "deadbeef" * 4
    digest = mod.hash_refresh_token(raw)
    user = mod.User(
        id=user_id,
        email="a@b.co",
        role="admin",
        created_at=mod.datetime.now(mod.timezone.utc),
    )

    conn = MagicMock()
    cur = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    cur.fetchone.side_effect = [(user_id,), None]
    cur.fetchall.return_value = []

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        with patch.object(mod, "get_user_by_id", return_value=user) as get_user:
            out = mod.validate_refresh_token(raw)

    assert out == user
    first_sql = cur.execute.call_args_list[0][0][0]
    assert "token_hash = %s" in first_sql
    assert cur.execute.call_args_list[0][0][1] == (digest,)
    get_user.assert_called_once_with(user_id)
