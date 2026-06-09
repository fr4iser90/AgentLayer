"""Unit tests for IDOR assertion helpers (mock HTTP, no live server)."""

from __future__ import annotations

import pytest

from tests.e2e.support.helpers import E2EClient
from tests.e2e.support.idor import assert_cross_user_get_blocked


class _FakeResp:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


def test_assert_cross_user_get_blocked_passes_when_other_denied() -> None:
    class _OwnerHttp:
        def get(self, path: str) -> _FakeResp:
            return _FakeResp(200)

    class _OtherHttp:
        def get(self, path: str) -> _FakeResp:
            return _FakeResp(404)

    owner = E2EClient(http=_OwnerHttp(), token="t", user_id="1", role="admin", email="a@test")  # type: ignore[arg-type]
    other = E2EClient(http=_OtherHttp(), token="t", user_id="2", role="user", email="b@test")  # type: ignore[arg-type]

    assert_cross_user_get_blocked(
        owner=owner,
        other=other,
        path="/v1/user/conversations/x",
        resource_label="conversation",
    )


def test_assert_cross_user_get_blocked_fails_on_idor() -> None:
    class _OwnerHttp:
        def get(self, path: str) -> _FakeResp:
            return _FakeResp(200)

    class _OtherHttp:
        def get(self, path: str) -> _FakeResp:
            return _FakeResp(200, '{"conversation":{"id":"x"}}')

    owner = E2EClient(http=_OwnerHttp(), token="t", user_id="1", role="admin", email="a@test")  # type: ignore[arg-type]
    other = E2EClient(http=_OtherHttp(), token="t", user_id="2", role="user", email="b@test")  # type: ignore[arg-type]

    with pytest.raises(BaseException, match="SECURITY FAIL"):
        assert_cross_user_get_blocked(
            owner=owner,
            other=other,
            path="/v1/user/conversations/x",
            resource_label="conversation",
        )
