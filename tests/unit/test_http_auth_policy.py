"""Unit tests for HTTP auth route classification (no running server required)."""

from __future__ import annotations

from apps.backend.api.platform.controllers.optional_http_access import (
    is_dashboard_public_share_route,
    is_identity_deferred_route,
    is_media_stream_route,
    middleware_path_is_public,
    public_http_auth_policy,
)


def test_public_health_and_auth_paths() -> None:
    assert middleware_path_is_public("/health", "GET")
    assert middleware_path_is_public("/auth/login", "POST")
    assert middleware_path_is_public("/auth/policy", "GET")
    assert middleware_path_is_public("/app/chat", "GET")
    assert not middleware_path_is_public("/v1/dashboards", "GET")


def test_otp_register_public_post_only() -> None:
    assert middleware_path_is_public("/v1/user/secrets/register-with-otp", "POST")
    assert not middleware_path_is_public("/v1/user/secrets/register-with-otp", "GET")


def test_identity_deferred_chat_and_tools() -> None:
    assert is_identity_deferred_route("/v1/chat/completions", "POST")
    assert is_identity_deferred_route("/tools/run", "POST")
    assert is_identity_deferred_route("/v1/tools", "GET")
    assert not is_identity_deferred_route("/v1/dashboards", "GET")


def test_media_stream_route_uuid_pattern() -> None:
    assert is_media_stream_route(
        "/v1/media/items/f61060dc-0c30-4648-a8d4-57aa5655d36d/stream",
        "GET",
    )
    assert not is_media_stream_route("/v1/media/items", "GET")


def test_dashboard_public_share_route_anon_get() -> None:
    assert is_dashboard_public_share_route(
        "/v1/dashboards/shared/NA-ndpGKwo6vD1dryUO2BtRsnyYdlwWQVttk8WJZgAc",
        "GET",
    )
    assert is_dashboard_public_share_route(
        "/v1/dashboards/shared/NA-ndpGKwo6vD1dryUO2BtRsnyYdlwWQVttk8WJZgAc/files/f61060dc-0c30-4648-a8d4-57aa5655d36d/content",
        "GET",
    )
    assert not is_dashboard_public_share_route("/v1/dashboards/shared/short", "GET")
    assert not is_dashboard_public_share_route("/v1/dashboards", "GET")


def test_public_policy_documents_admin_routes() -> None:
    policy = public_http_auth_policy()
    admin = policy.get("admin_routes") or []
    joined = "\n".join(str(x) for x in admin)
    assert "operator-settings" in joined
    assert "tool-policies" in joined
