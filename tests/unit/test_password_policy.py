"""Password policy: structural rules only (no word denylist)."""

from __future__ import annotations

from apps.backend.domain.identity.password_policy import (
    password_rejection_reason,
    password_strength_level,
)


def test_rejects_short_and_simple() -> None:
    assert password_rejection_reason("test1234") is not None
    assert password_strength_level("test1234") == 1


def test_rejects_missing_symbol() -> None:
    assert password_rejection_reason("Abcdefghijkl1") is not None


def test_rejects_sequence() -> None:
    assert password_rejection_reason("Abcd1234!!!!") is not None


def test_accepts_diverse_secret() -> None:
    assert password_rejection_reason("MyStr0ng!Pass") is None
    assert password_strength_level("MyStr0ng!Pass") >= 2
