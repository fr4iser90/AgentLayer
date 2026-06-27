"""Tests for media sharing policy helpers."""

from __future__ import annotations

from apps.backend.infrastructure.media import media_policy


def test_normalize_media_license() -> None:
    assert media_policy.normalize_media_license("owned") == "owned"
    assert media_policy.normalize_media_license("CC-BY") == "cc-by"
    assert media_policy.normalize_media_license("invalid") is None


def test_item_is_shareable() -> None:
    assert media_policy.item_is_shareable({"source_kind": "upload", "license": "owned"}) is True
    assert media_policy.item_is_shareable({"source_kind": "upload", "license": None}) is False
    assert media_policy.item_is_shareable({"source_kind": "embed", "license": "owned"}) is False
