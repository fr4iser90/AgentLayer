"""Provider schema and invariant validation."""
from __future__ import annotations

from typing import Any

_ALLOWED_HEADERS = frozenset({"authorization", "x-api-key", "x-goog-api-key"})


def validate_provider_base_url(raw: str) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        raise ValueError("provider base_url must be http(s)")
    if len(value) > 2048:
        raise ValueError("provider base_url is too long")
    return value


def validate_api_header_name(raw: str | None) -> str:
    value = (raw or "Authorization").strip()
    if not value:
        return "Authorization"
    if value.lower() not in _ALLOWED_HEADERS and len(value) > 128:
        raise ValueError("provider api header name is too long")
    return value[:128]


def validate_api_key(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > 1024:
        raise ValueError("provider api key is too long")
    return value


def validate_model_id(raw: str | None) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    if len(value) > 256:
        raise ValueError("model id must be <= 256 characters")
    return value


def validate_provider_options(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("provider options must be an object")
    return dict(raw)


def validate_max_parallel(raw: int | None) -> int:
    value = int(raw or 1)
    if value < 1 or value > 128:
        raise ValueError("provider max_parallel must be between 1 and 128")
    return value
