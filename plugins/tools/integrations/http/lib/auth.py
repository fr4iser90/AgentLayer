"""Build HTTP auth headers/params from user secrets (never returned to the model)."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.identity.secret_otp_bundle import validate_user_secret_service_key


def _parse_secret_value(raw: str) -> str | dict[str, Any]:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return s
    return obj if isinstance(obj, dict) else s


def _token_from_secret_obj(obj: Any) -> str:
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, dict):
        for key in ("token", "pat", "api_key", "key", "password", "secret"):
            v = obj.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
    return ""


def resolve_auth(
    user_id: uuid.UUID,
    auth: dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, str], str | None]:
    """
    Return (extra_headers, query_params, error).
    Auth spec shapes:
    - ``{"type": "none"}`` or omitted
    - ``{"type": "bearer", "secret_key": "my_api"}``
    - ``{"type": "api_key_header", "secret_key": "...", "header": "X-API-Key"}``
    - ``{"type": "api_key_query", "secret_key": "...", "param": "api_key"}``
    - ``{"type": "basic", "secret_key": "..."}`` — secret JSON ``{username, password}`` or ``user:pass``
    """
    if not auth or not isinstance(auth, dict):
        return {}, {}, None
    typ = str(auth.get("type") or "none").strip().lower()
    if typ in ("", "none"):
        return {}, {}, None

    sk_raw = auth.get("secret_key")
    sk = validate_user_secret_service_key(str(sk_raw).strip() if sk_raw is not None else "")
    if not sk:
        return {}, {}, "auth.secret_key required and must be a valid service_key name"

    raw = db.user_secret_get_plaintext(user_id, sk)
    if not raw:
        return (
            {},
            {},
            f"No secret for service_key {sk!r} — use save_user_secret or Settings → Connections",
        )

    parsed = _parse_secret_value(raw)

    if typ == "bearer":
        token = _token_from_secret_obj(parsed)
        if not token:
            return {}, {}, f"Secret {sk!r} has no bearer token"
        return {"Authorization": f"Bearer {token}"}, {}, None

    if typ == "api_key_header":
        header = str(auth.get("header") or "X-API-Key").strip() or "X-API-Key"
        token = _token_from_secret_obj(parsed)
        if not token:
            return {}, {}, f"Secret {sk!r} has no api key value"
        return {header: token}, {}, None

    if typ == "api_key_query":
        param = str(auth.get("param") or "api_key").strip() or "api_key"
        token = _token_from_secret_obj(parsed)
        if not token:
            return {}, {}, f"Secret {sk!r} has no api key value"
        return {}, {param: token}, None

    if typ == "basic":
        user = ""
        password = ""
        if isinstance(parsed, dict):
            user = str(parsed.get("username") or parsed.get("user") or "").strip()
            password = str(parsed.get("password") or parsed.get("pass") or "").strip()
        elif isinstance(parsed, str) and ":" in parsed:
            user, _, password = parsed.partition(":")
            user, password = user.strip(), password.strip()
        if not user or not password:
            return {}, {}, f"Secret {sk!r} must be JSON {{username, password}} or user:pass"
        import base64

        cred = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {cred}"}, {}, None

    return {}, {}, f"unsupported auth.type {typ!r}"
