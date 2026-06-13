"""Resolve mail provider + credentials for the current user."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from apps.backend.domain.identity import get_identity
from plugins.tools.integrations.mail.lib.providers import MAIL_PROVIDERS, MailProviderSpec
from apps.backend.infrastructure.db import db


@dataclass
class MailSession:
    provider: MailProviderSpec
    email: str
    password: str


def _normalize_password(raw: str, *, strip_spaces: bool) -> str:
    pw = raw.strip()
    return pw.replace(" ", "") if strip_spaces else pw


def _parse_secret_json(raw: str, *, strip_pw_spaces: bool) -> dict[str, str] | None:
    try:
        obj = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    email = str(obj.get("email") or "").strip()
    pw = _normalize_password(
        str(obj.get("app_password") or obj.get("password") or ""),
        strip_spaces=strip_pw_spaces,
    )
    if not email or not pw:
        return None
    out = {"email": email, "password": pw}
    prov = str(obj.get("provider") or "").strip().lower()
    if prov:
        out["provider"] = prov
    return out


def _load_from_service_key(user_id: int, service_key: str) -> dict[str, str] | None:
    raw = db.user_secret_get_plaintext(user_id, service_key)
    if not raw:
        return None
    strip = service_key == "gmail"
    parsed = _parse_secret_json(raw, strip_pw_spaces=strip)
    if not parsed:
        return None
    if service_key == "mail" and parsed.get("provider"):
        return parsed
    if service_key in MAIL_PROVIDERS:
        parsed.setdefault("provider", service_key)
    return parsed


def resolve_mail_session(
    arguments: dict[str, Any] | None = None,
) -> MailSession | str:
    """Return ``MailSession`` or an error string for JSON responses."""
    _tid, uid = get_identity()
    if uid is None:
        return "No user identity in this request (need chat/user headers for per-user mail secrets)."

    args = arguments or {}
    want = str(args.get("provider") or "").strip().lower()

    candidates: list[tuple[str, dict[str, str]]] = []
    for spec in MAIL_PROVIDERS.values():
        if want and spec.id != want:
            continue
        for key in spec.secret_keys:
            row = _load_from_service_key(uid, key)
            if not row:
                continue
            prov_id = str(row.get("provider") or spec.id).lower()
            if prov_id not in MAIL_PROVIDERS:
                continue
            if want and prov_id != want:
                continue
            candidates.append((prov_id, row))

    if not candidates:
        if want:
            return (
                f"No mail credentials for provider {want!r}. "
                f"Store a secret (service_key {want!r} or mail JSON with provider)."
            )
        return (
            "No mail credentials configured. Connect Gmail, Outlook, GMX, Yahoo, or Proton "
            "under Settings → Connections, or pass provider=… when multiple are set."
        )

    prov_id, row = candidates[0]
    spec = MAIL_PROVIDERS[prov_id]
    return MailSession(provider=spec, email=row["email"], password=row["password"])


def sanitize_query(query: str, *, provider: MailProviderSpec) -> str:
    q = (query or "").strip()
    if not q:
        return provider.default_query
    q = re.sub(r'["\\\x00\r\n]', " ", q)
    return q[:800] or provider.default_query
