"""
HTTP auth middleware helpers: fully public paths vs routes that defer Bearer checks.

Some API routes skip the global ``get_current_user`` middleware gate; each handler
still enforces JWT / user API key (or anonymous catalog where explicitly supported)
via ``http_identity``.
"""

from __future__ import annotations

import re
from typing import Any

_MEDIA_STREAM_PATH_RE = re.compile(
    r"^/v1/media/items/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/stream$",
    re.IGNORECASE,
)

_DASHBOARD_PUBLIC_SHARE_PATH_RE = re.compile(
    r"^/v1/dashboards/shared/[^/]{16,}(?:/files/[0-9a-f-]{36}/content)?$",
    re.IGNORECASE,
)

_MIDDLEWARE_PUBLIC_EXACT: frozenset[str] = frozenset(
    {
        "/",
        "/health",
        "/v1/models",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/setup-status",
        "/auth/setup",
        "/auth/policy",
        "/favicon.ico",
        "/login",
        "/chat",
        "/dashboard",
    }
)


def middleware_path_is_public(path: str, method: str) -> bool:
    """Paths that skip global Bearer/JWT checks entirely."""
    if path.startswith("/js/"):
        return True
    if path == "/app" or path.startswith("/app/"):
        return True
    if path in _MIDDLEWARE_PUBLIC_EXACT:
        return True
    if (method or "").upper() == "POST" and path == "/v1/user/secrets/register-with-otp":
        return True
    return False


def is_identity_deferred_route(path: str, method: str) -> bool:
    """Routes that skip global JWT middleware; handlers resolve Bearer themselves."""
    m = (method or "").upper()
    if m == "POST" and path == "/v1/chat/completions":
        return True
    if m == "POST" and path == "/tools/run":
        return True
    if m == "GET" and path == "/v1/tools":
        return True
    if m == "GET" and path == "/v1/capabilities":
        return True
    if m == "GET" and path == "/v1/router/categories":
        return True
    if m == "GET" and (
        path == "/openapi.json"
        or path == "/openapi/domains"
        or path.startswith("/openapi/")
    ):
        return True
    return False


def is_media_stream_route(path: str, method: str) -> bool:
    """``<audio src>`` uses ``?token=`` — handler validates Bearer or query token."""
    return (method or "").upper() == "GET" and bool(_MEDIA_STREAM_PATH_RE.match(path))


def is_dashboard_public_share_route(path: str, method: str) -> bool:
    """Read-only dashboard share links (token in path; optional link password in handler)."""
    return (method or "").upper() == "GET" and bool(_DASHBOARD_PUBLIC_SHARE_PATH_RE.match(path))


def public_http_auth_policy() -> dict[str, Any]:
    """Machine-readable policy for ``GET /auth/policy``."""
    return {
        "description": (
            "Middleware order: public paths → identity-deferred routes (no global JWT) → "
            "JWT/API key for all other routes."
        ),
        "middleware": {
            "options_preflight": "OPTIONS passes without Authorization.",
            "no_authorization": {
                "exact_paths": sorted(_MIDDLEWARE_PUBLIC_EXACT),
                "path_prefixes": ["/js/", "/app/"],
                "post_path": "/v1/user/secrets/register-with-otp",
                "get_path_patterns": [
                    "/v1/media/items/{uuid}/stream",
                    "/v1/dashboards/shared/{token}",
                    "/v1/dashboards/shared/{token}/files/{uuid}/content",
                ],
            },
            "identity_deferred_routes": {
                "note": (
                    "These skip the global middleware Bearer check; each handler requires "
                    "JWT or user API key where applicable (e.g. chat), or serves anonymous "
                    "data where documented (e.g. tool catalog)."
                ),
                "routes": [
                    {"method": "WebSocket", "path": "/ws/v1/chat"},
                    {"method": "POST", "path": "/v1/chat/completions"},
                    {"method": "POST", "path": "/tools/run"},
                    {"method": "GET", "path": "/v1/tools"},
                    {"method": "GET", "path": "/v1/capabilities"},
                    {"method": "GET", "path": "/v1/router/categories"},
                    {"method": "GET", "path": "/openapi.json"},
                    {"method": "GET", "path": "/openapi/domains"},
                    {"method": "GET", "path_prefix": "/openapi/"},
                ],
            },
            "all_other_routes": "Valid JWT access token or api_keys entry in Authorization: Bearer.",
        },
        "admin_routes": [
            "GET/PUT/PATCH /v1/admin/operator-settings",
            "POST /v1/admin/external-llm/models",
            "GET/PUT /v1/admin/interfaces",
            "GET/POST /v1/admin/tenants",
            "GET /v1/admin/users",
            "POST /v1/admin/users",
            "PATCH /v1/admin/users/{user_id}",
            "PUT /v1/admin/tool-policies",
            "POST /v1/admin/rag/ingest",
            "POST /v1/admin/rag/ingest-docs",
        ],
        "note_admin": "Bearer must resolve to a user with role=admin; then require_admin().",
        "note_identity": (
            "User/tenant for chat, tools, RAG, user APIs: JWT or API key only; "
            "tenant = users.tenant_id. Identity headers are not used."
        ),
    }
