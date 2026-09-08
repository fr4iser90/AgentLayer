"""Unit tests for API key minting, hashed lookup and expiry enforcement."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from apps.backend.infrastructure.identity import auth as mod


def _mock_conn() -> tuple[MagicMock, MagicMock]:
    conn = MagicMock()
    cur = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    return conn, cur


def _user(user_id: uuid.UUID) -> mod.User:
    return mod.User(
        id=user_id,
        email="a@b.co",
        role="user",
        created_at=mod.datetime.now(mod.timezone.utc),
    )


def test_hash_api_key_is_sha256_hex() -> None:
    h = mod.hash_api_key("abc")
    assert len(h) == 64
    assert h == mod.hash_api_key("abc")
    assert h != mod.hash_api_key("abd")


def test_generated_keys_are_prefixed_and_unique() -> None:
    a = mod.generate_api_key()
    b = mod.generate_api_key()
    assert a.startswith(mod.API_KEY_PREFIX)
    assert a != b
    assert len(a) > len(mod.API_KEY_PREFIX) + 20


def test_create_api_key_stores_digest_never_the_secret() -> None:
    user_id = uuid.uuid4()
    conn, cur = _mock_conn()
    cur.fetchone.return_value = (
        uuid.uuid4(),
        "tui",
        mod.datetime.now(mod.timezone.utc),
        None,
        None,
    )

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        token, meta = mod.create_api_key(user_id, "tui")

    params = cur.execute.call_args_list[0][0][1]
    assert token not in params, "the raw secret must not be written to the database"
    assert mod.hash_api_key(token) in params
    assert meta["name"] == "tui"


def test_bearer_lookup_hashes_the_presented_token() -> None:
    user_id = uuid.uuid4()
    raw = "al_" + "z" * 32
    conn, cur = _mock_conn()
    cur.fetchone.return_value = (user_id,)

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        with patch.object(mod, "decode_access_token", return_value=None):
            with patch(
                "apps.backend.infrastructure.platform.client_surface_policy.refuse_api_key_auth",
                return_value=None,
            ):
                with patch.object(mod, "get_user_by_id", return_value=_user(user_id)) as get_user:
                    out = mod.get_user_for_bearer_token(raw)

    assert out is not None
    sql, params = cur.execute.call_args_list[0][0][0], cur.execute.call_args_list[0][0][1]
    assert "key_hash = %s" in sql
    assert params == (mod.hash_api_key(raw),)
    assert raw not in params
    get_user.assert_called_once_with(user_id)


def test_bearer_lookup_rejects_expired_keys_in_sql() -> None:
    conn, cur = _mock_conn()
    cur.fetchone.return_value = None

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        with patch.object(mod, "decode_access_token", return_value=None):
            with patch(
                "apps.backend.infrastructure.platform.client_surface_policy.refuse_api_key_auth",
                return_value=None,
            ):
                out = mod.get_user_for_bearer_token("al_expired")

    assert out is None
    sql = cur.execute.call_args_list[0][0][0]
    assert "expires_at IS NULL OR expires_at > NOW()" in sql


def test_revoke_is_scoped_to_the_owning_user() -> None:
    user_id = uuid.uuid4()
    key_id = uuid.uuid4()
    conn, cur = _mock_conn()
    cur.rowcount = 0

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        assert mod.revoke_api_key(user_id, key_id) is False

    sql, params = cur.execute.call_args_list[0][0][0], cur.execute.call_args_list[0][0][1]
    assert "user_id = %s" in sql
    assert params == (key_id, user_id)


def test_list_marks_expired_keys() -> None:
    now = mod.datetime.now(mod.timezone.utc)
    conn, cur = _mock_conn()
    cur.fetchall.return_value = [
        (uuid.uuid4(), "old", now, None, now - mod.timedelta(days=1)),
        (uuid.uuid4(), "live", now, None, now + mod.timedelta(days=1)),
        (uuid.uuid4(), "forever", now, None, None),
    ]

    with patch.object(mod.db, "pool") as pool_mock:
        pool_mock.return_value.connection.return_value = conn
        rows = mod.list_api_keys(uuid.uuid4())

    assert [r["expired"] for r in rows] == [True, False, False]
    assert all("key_hash" not in r for r in rows)


def test_interactive_session_distinguishes_jwt_from_api_key() -> None:
    with patch.object(mod, "decode_access_token", return_value={"sub": "x"}):
        assert mod.bearer_is_interactive_session("a.jwt.token") is True
    with patch.object(mod, "decode_access_token", return_value=None):
        assert mod.bearer_is_interactive_session("al_somekey") is False
    assert mod.bearer_is_interactive_session("") is False
