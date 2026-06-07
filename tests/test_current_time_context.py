"""Tests for per-user/request date/time system injection."""

from __future__ import annotations

import re
import uuid
from unittest import mock

from apps.backend.domain.current_time_context import (
    apply_current_time_context,
    build_current_time_context_snippet,
    resolve_user_timezone,
)


def test_snippet_with_timezone() -> None:
    text = build_current_time_context_snippet(timezone_name="Europe/Berlin")
    assert "user's timezone" in text
    assert "Europe/Berlin" in text
    assert re.search(r"Today: \d{4}-\d{2}-\d{2}", text)


def test_snippet_without_timezone_no_fake_local() -> None:
    text = build_current_time_context_snippet(timezone_name=None)
    assert "not stored yet" in text
    assert "Do not infer local wall-clock" in text
    assert "Local time:" not in text


def test_request_timezone_persisted_and_used() -> None:
    uid = uuid.uuid4()
    with mock.patch(
        "apps.backend.domain.current_time_context._persist_request_timezone"
    ) as mock_persist:
        tz = resolve_user_timezone(
            uid,
            1,
            request_timezone="Europe/Berlin",
        )
    assert tz == "Europe/Berlin"
    mock_persist.assert_called_once_with(uid, 1, "Europe/Berlin")


def test_profile_timezone_when_no_request() -> None:
    uid = uuid.uuid4()
    with mock.patch(
        "apps.backend.domain.current_time_context._profile_timezone",
        return_value="Europe/Vienna",
    ):
        tz = resolve_user_timezone(uid, 1, request_timezone=None)
    assert tz == "Europe/Vienna"


def test_no_timezone_returns_none_not_utc() -> None:
    uid = uuid.uuid4()
    with mock.patch(
        "apps.backend.domain.current_time_context._profile_timezone",
        return_value=None,
    ):
        tz = resolve_user_timezone(uid, 1, request_timezone=None)
    assert tz is None


def test_apply_uses_request_timezone() -> None:
    uid = uuid.uuid4()
    out = apply_current_time_context(
        [{"role": "user", "content": "hi"}],
        uid,
        1,
        request_timezone="Europe/Berlin",
    )
    assert out[0]["role"] == "system"
    assert "Europe/Berlin" in str(out[0]["content"])
