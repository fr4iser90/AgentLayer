"""Media stream route bypasses global Bearer-only middleware."""

from __future__ import annotations

from apps.backend.api.optional_http_access import is_media_stream_route


def test_media_stream_route_matches_uuid_path() -> None:
    assert is_media_stream_route(
        "/v1/media/items/f61060dc-0c30-4648-a8d4-57aa5655d36d/stream",
        "GET",
    )


def test_media_stream_route_rejects_list() -> None:
    assert not is_media_stream_route("/v1/media/items", "GET")


def test_media_stream_route_rejects_post() -> None:
    assert not is_media_stream_route(
        "/v1/media/items/f61060dc-0c30-4648-a8d4-57aa5655d36d/stream",
        "POST",
    )
