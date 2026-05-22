"""First-instance setup: admin registration and LLM endpoint configuration."""

from __future__ import annotations

import json
import logging
import re
import secrets
import sys
import threading
import time
from collections import defaultdict
from typing import Any, Literal

import httpx
from fastapi import HTTPException, Request

from apps.backend.core.config import AGENT_SETUP_TOKEN

from apps.backend.domain.admin_setup import is_first_start, try_create_initial_admin_from_env
from apps.backend.domain.catalog_chat_llm import pick_reachable_catalog_provider
from apps.backend.infrastructure.auth import User, insert_user_with_cursor
from apps.backend.dashboard.db import ensure_default_dashboard_for_new_user
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.operator_settings import (
    external_api_headers,
    external_models_list_url,
    invalidate_operator_settings_cache,
)
from apps.backend.infrastructure.model_catalog_routing import invalidate_model_catalog_cache

logger = logging.getLogger(__name__)

_SETUP_LOCK_ID = 872814001
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NO_AUTH_API_KEY_PLACEHOLDER = "-"

_rate_lock = threading.Lock()
_setup_attempts: dict[str, list[float]] = defaultdict(list)
_SETUP_RATE_WINDOW_SEC = 3600.0
_SETUP_RATE_MAX = 10

_token_init_lock = threading.Lock()
_runtime_auto_setup_token: str | None = None
_setup_banner_logged = False


def _client_id(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()[:200] or "unknown"
    if request.client and request.client.host:
        return request.client.host.strip()[:200]
    return "unknown"


def enforce_setup_rate_limit(request: Request) -> None:
    cid = _client_id(request)
    now = time.monotonic()
    with _rate_lock:
        lst = _setup_attempts[cid]
        cutoff = now - _SETUP_RATE_WINDOW_SEC
        lst[:] = [t for t in lst if t > cutoff]
        if len(lst) >= _SETUP_RATE_MAX:
            raise HTTPException(
                status_code=429,
                detail="Zu viele Versuche. Bitte später erneut versuchen.",
            )
        lst.append(now)


def validate_setup_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not e or not _EMAIL_RE.match(e):
        raise HTTPException(status_code=400, detail="Ungültige E-Mail-Adresse.")
    return e


def _setup_token_from_env() -> str | None:
    t = (AGENT_SETUP_TOKEN or "").strip()
    return t or None


def setup_token_source() -> Literal["env", "auto"] | None:
    """How the setup token is defined (never returns the secret)."""
    if not is_first_start():
        return None
    if _setup_token_from_env():
        return "env"
    return "auto"


def ensure_setup_token_materialized() -> str:
    """Expected setup token: ``AGENT_SETUP_TOKEN`` or frozen auto-generated value."""
    env_tok = _setup_token_from_env()
    if env_tok:
        return env_tok
    global _runtime_auto_setup_token
    with _token_init_lock:
        if _runtime_auto_setup_token is None:
            _runtime_auto_setup_token = secrets.token_urlsafe(32)
        return _runtime_auto_setup_token


def _write_setup_banner(lines: list[str]) -> None:
    """stderr block without per-line ``apps.backend...`` logger prefixes (docker-friendly)."""
    print("\n".join(lines), file=sys.stderr, flush=True)


def log_setup_token_banner_if_needed() -> None:
    """Log setup instructions once per process while no admin exists."""
    global _setup_banner_logged
    if not is_first_start():
        return
    with _token_init_lock:
        if _setup_banner_logged:
            return
        _setup_banner_logged = True

    if _setup_token_from_env():
        _write_setup_banner(
            [
                "",
                "======== AgentLayer — Ersteinrichtung ========",
                "Administrator fehlt. Öffnen: /app/setup",
                "Einrichtungs-Token: Wert aus AGENT_SETUP_TOKEN in .env",
                "(Token wird hier nicht geloggt.)",
                "=============================================",
                "",
            ]
        )
        return

    token = ensure_setup_token_materialized()
    _write_setup_banner(
        [
            "",
            "======== AgentLayer — Ersteinrichtung ========",
            "Administrator fehlt. Öffnen: /app/setup",
            "Öffentliche Hosts: AGENT_SETUP_TOKEN in .env setzen.",
            "",
            "Einrichtungs-Token:",
            token,
            "=============================================",
            "",
        ]
    )


def emit_initial_setup_notice_at_end() -> None:
    """Call at end of application startup so the token is the last log block."""
    log_setup_token_banner_if_needed()


def validate_setup_token(provided: str | None) -> None:
    if not is_first_start():
        return
    expected = ensure_setup_token_materialized()
    got = (provided or "").strip()
    if not got or got != expected:
        raise HTTPException(status_code=403, detail="Ungültiges Einrichtungs-Token.")


def validate_setup_password(password: str, password_confirm: str | None = None) -> None:
    p = password or ""
    if len(p) < 8:
        raise HTTPException(
            status_code=400,
            detail="Passwort: mindestens 8 Zeichen.",
        )
    if password_confirm is not None and p != (password_confirm or ""):
        raise HTTPException(status_code=400, detail="Die Passwörter stimmen nicht überein.")


def create_first_admin(*, email: str, password: str) -> User:
    if not is_first_start():
        raise HTTPException(
            status_code=409,
            detail="Die Ersteinrichtung wurde bereits abgeschlossen.",
        )
    e = validate_setup_email(email)
    validate_setup_password(password)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_SETUP_LOCK_ID,))
            cur.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            if cur.fetchone()[0] > 0:
                conn.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="Die Ersteinrichtung wurde bereits abgeschlossen.",
                )
            user = insert_user_with_cursor(cur, e, password, role="admin")
            cur.execute("DELETE FROM admin_claim_otp")
        conn.commit()

    ensure_default_dashboard_for_new_user(user.id, 1)
    logger.info("First admin created via setup (email=%s)", e)
    return user


def catalog_llm_configured() -> bool:
    return pick_reachable_catalog_provider() is not None


def setup_preferences_saved() -> bool:
    """True after setup wizard saved provider profile models to DB."""
    try:
        for row in db.external_llm_endpoints_list_all():
            if (str(row.get("model_agent") or "")).strip():
                return True
            if (str(row.get("model_coding") or "")).strip():
                return True
    except Exception:
        return False
    return False


def build_setup_status() -> dict[str, Any]:
    needs_admin = is_first_start()
    llm_configured = catalog_llm_configured() if not needs_admin else False
    needs_llm = not needs_admin and not llm_configured
    needs_provider_wizard = not needs_admin and not setup_preferences_saved()
    llm_reachable = llm_configured
    src = setup_token_source()
    return {
        "needs_setup": needs_admin,
        "needs_admin": needs_admin,
        "needs_llm": needs_llm,
        "needs_provider_wizard": needs_provider_wizard,
        "llm_reachable": llm_reachable,
        "setup_token_required": bool(needs_admin),
        "setup_token_source": src,
    }


def _normalize_base_url(raw: str) -> str:
    u = (raw or "").strip().rstrip("/")
    if not u:
        raise HTTPException(status_code=400, detail="Basis-URL ist erforderlich.")
    if not u.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Basis-URL muss mit http:// oder https:// beginnen.")
    return u


def _effective_api_key(api_key: str | None) -> str:
    k = (api_key or "").strip()
    return k if k else _NO_AUTH_API_KEY_PLACEHOLDER


async def probe_llm_endpoint(*, base_url: str, api_key: str | None) -> dict[str, Any]:
    bu = _normalize_base_url(base_url)
    key = _effective_api_key(api_key)
    url = external_models_list_url(bu)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=external_api_headers(bu, key),
                timeout=httpx.Timeout(45.0),
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Der Endpunkt ist nicht erreichbar. Prüfen Sie URL, Netzwerk und ob der Dienst läuft.",
        ) from exc
    if resp.status_code == 401 or resp.status_code == 403:
        raise HTTPException(
            status_code=resp.status_code,
            detail="Authentifizierung fehlgeschlagen. Prüfen Sie den API-Schlüssel.",
        )
    if resp.status_code != 200:
        snippet = (resp.text or "").strip()[:500]
        raise HTTPException(
            status_code=502,
            detail=snippet or f"HTTP {resp.status_code}",
        )
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Antwort der API war kein JSON.") from exc

    models: list[str] = []
    raw = data.get("data") if isinstance(data, dict) else None
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                mid = item.get("id") or item.get("name")
                if mid:
                    models.append(str(mid))
    return {"ok": True, "model_count": len(models), "models": models[:50]}


def apply_setup_llm_endpoint(
    *,
    base_url: str,
    api_key: str | None,
    model_default: str | None,
    label: str | None,
) -> None:
    bu = _normalize_base_url(base_url)
    key = _effective_api_key(api_key)
    md = (model_default or "").strip() or None
    lbl = (label or "").strip()[:512] or "LLM"

    row: dict[str, Any] = {
        "sort_order": 0,
        "enabled": True,
        "label": lbl,
        "base_url": bu,
        "api_key": key,
        "model_default": md,
        "model_vlm": None,
        "model_agent": md,
        "model_coding": md,
    }
    try:
        db.external_llm_endpoints_sync([row])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    invalidate_operator_settings_cache()
    invalidate_model_catalog_cache()


def setup_admin_claim_if_needed() -> None:
    """Env bootstrap optional; otherwise wait for POST /auth/setup."""
    if not is_first_start():
        return
    if try_create_initial_admin_from_env():
        return
    logger.info(
        "No administrator account yet. Complete initial setup at /app/setup or set "
        "AGENT_INITIAL_ADMIN_EMAIL and AGENT_INITIAL_ADMIN_PASSWORD."
    )
