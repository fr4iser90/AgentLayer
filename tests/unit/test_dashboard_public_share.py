"""Tests for dashboard public share helpers."""

from __future__ import annotations

from apps.backend.infrastructure.dashboards import dashboard_public_share as public_share
from apps.backend.domain.collections.attachments_db import file_ids_in_value


def test_hash_share_token_deterministic() -> None:
    a = public_share.hash_share_token("abc")
    b = public_share.hash_share_token("abc")
    assert a == b
    assert a != public_share.hash_share_token("abcd")


def test_hash_share_password_bound_to_token_hash() -> None:
    th = public_share.hash_share_token("raw-token")
    a = public_share.hash_share_password(th, "secret")
    b = public_share.hash_share_password(th, "secret")
    c = public_share.hash_share_password(public_share.hash_share_token("other"), "secret")
    assert a == b
    assert a != c


def test_file_ids_in_nested_data() -> None:
    data = {
        "photos": [{"url": "file:111", "caption": "a"}],
        "albums": [{"photos": [{"url": "https://x.test/p.jpg"}, {"url": "file:222"}]}],
        "notes": "plain",
    }
    ids = file_ids_in_value(data)
    assert ids == {"111", "222"}


def test_password_check_states() -> None:
    th = public_share.hash_share_token("tok")
    row_open = {"password_hash": None, "token_hash": th}
    row_locked = {
        "password_hash": public_share.hash_share_password(th, "hunde"),
        "token_hash": th,
    }
    assert public_share._password_check(row_open, None) == "ok"
    assert public_share._password_check(row_open, "x") == "ok"
    assert public_share._password_check(row_locked, None) == "password_required"
    assert public_share._password_check(row_locked, "wrong") == "invalid_password"
    assert public_share._password_check(row_locked, "hunde") == "ok"
