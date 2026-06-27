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
from typing import Any, Literal, Protocol

import httpx
from fastapi import HTTPException, Request

from apps.backend.core.config import AGENT_SETUP_TOKEN

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
User = Any


class InstanceSetupDependencies(Protocol):
    def is_first_start(self) -> bool: ...

    def try_create_initial_admin_from_env(self) -> bool: ...

    def cached_llm_reachable(self) -> bool | None: ...

    def list_provider_specs(self) -> list[Any]: ...

    def pool(self) -> Any: ...

    def insert_user_with_cursor(self, cur: Any, email: str, password: str, *, role: str) -> Any: ...

    def ensure_default_dashboard_for_new_user(self, user_id: Any, tenant_id: int) -> None: ...

    def operator_provider_endpoints_list_all(self, kind: str) -> list[dict[str, Any]]: ...

    def external_llm_endpoints_list_all(self) -> list[dict[str, Any]]: ...

    def operator_provider_endpoints_sync(
        self, kind: str, rows: list[dict[str, Any]], *, delete_missing: bool = True
    ) -> None: ...

    def external_api_headers(self, base_url: str, api_key: str) -> dict[str, str]: ...

    def external_models_list_url(self, base_url: str) -> str: ...

    def invalidate_operator_settings_cache(self) -> None: ...

    def invalidate_model_catalog_cache(self) -> None: ...


_deps: InstanceSetupDependencies | None = None


def register_instance_setup_dependencies(deps: InstanceSetupDependencies) -> None:
    global _deps
    _deps = deps


def _require_deps() -> InstanceSetupDependencies:
    if _deps is None:
        raise RuntimeError("instance setup dependencies not registered")
    return _deps


def is_first_start() -> bool:
    return _require_deps().is_first_start()


def try_create_initial_admin_from_env() -> bool:
    return _require_deps().try_create_initial_admin_from_env()


def cached_llm_reachable() -> bool | None:
    return _require_deps().cached_llm_reachable()


def list_provider_specs() -> list[Any]:
    return _require_deps().list_provider_specs()


class _DbPort:
    def pool(self) -> Any:
        return _require_deps().pool()

    def operator_provider_endpoints_list_all(self, kind: str) -> list[dict[str, Any]]:
        return _require_deps().operator_provider_endpoints_list_all(kind)

    def external_llm_endpoints_list_all(self) -> list[dict[str, Any]]:
        return _require_deps().external_llm_endpoints_list_all()

    def operator_provider_endpoints_sync(
        self, kind: str, rows: list[dict[str, Any]], *, delete_missing: bool = True
    ) -> None:
        _require_deps().operator_provider_endpoints_sync(kind, rows, delete_missing=delete_missing)


db = _DbPort()


def insert_user_with_cursor(cur: Any, email: str, password: str, *, role: str) -> Any:
    return _require_deps().insert_user_with_cursor(cur, email, password, role=role)


def ensure_default_dashboard_for_new_user(user_id: Any, tenant_id: int) -> None:
    _require_deps().ensure_default_dashboard_for_new_user(user_id, tenant_id)


def external_api_headers(base_url: str, api_key: str) -> dict[str, str]:
    return _require_deps().external_api_headers(base_url, api_key)


def external_models_list_url(base_url: str) -> str:
    return _require_deps().external_models_list_url(base_url)


def invalidate_operator_settings_cache() -> None:
    _require_deps().invalidate_operator_settings_cache()


def invalidate_model_catalog_cache() -> None:
    _require_deps().invalidate_model_catalog_cache()


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
    """True when an LLM endpoint is configured (env/DB). No live HTTP probe — safe for /auth/setup-status."""
    for spec in list_provider_specs():
        if (spec.base_url or "").strip():
            return True
    return False


def setup_preferences_saved() -> bool:
    """True after setup wizard saved provider profile models to DB."""
    try:
        rows = db.operator_provider_endpoints_list_all("chat")
        if not rows:
            rows = db.external_llm_endpoints_list_all()
        for row in rows:
            if (str(row.get("model_default") or "")).strip():
                return True
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
    reachable = cached_llm_reachable()
    llm_reachable = reachable if reachable is not None else False
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
    }
    try:
        db.operator_provider_endpoints_sync("chat", [row], delete_missing=False)
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
