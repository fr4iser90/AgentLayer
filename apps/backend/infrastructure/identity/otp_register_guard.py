"""TLS expectation + per-IP sliding-window rate limit for ``POST /v1/user/secrets/register-with-otp``."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, Request

from apps.backend.infrastructure.platform.config import config

_lock = threading.Lock()
_attempts: dict[str, list[float]] = defaultdict(list)


def _effective_https(request: Request) -> bool:
    if (request.url.scheme or "").lower() == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return proto == "https"


def _loopback_request(request: Request) -> bool:
    c = request.client
    if c and c.host in ("127.0.0.1", "::1", "localhost"):
        return True
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return host in ("127.0.0.1", "localhost", "::1")


def require_https_or_loopback_for_otp_register(request: Request) -> None:
    """
    Reject cleartext from the public internet. Loopback HTTP is allowed for local dev.

    Behind Traefik, rely on ``X-Forwarded-Proto: https`` (set ``uvicorn --proxy-headers`` or equivalent).
    """
    if _loopback_request(request):
        return
    if _effective_https(request):
        return
    raise HTTPException(
        status_code=403,
        detail=(
            "HTTPS required for OTP secret registration. Use https:// in AGENT_PUBLIC_URL, "
            "terminate TLS at your reverse proxy, and forward X-Forwarded-Proto. "
            "Local development: call http://127.0.0.1 only."
        ),
    )


def client_id_for_otp_rate_limit(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").strip()
    if xff:
        return xff.split(",")[0].strip()[:200] or "unknown"
    if request.client and request.client.host:
        return request.client.host.strip()[:200]
    return "unknown"


def enforce_otp_register_rate_limit(request: Request) -> None:
    """In-process sliding window; key is first X-Forwarded-For hop or direct client IP."""
    cid = client_id_for_otp_rate_limit(request)
    now = time.monotonic()
    window = float(config.OTP_REGISTER_RATE_LIMIT_WINDOW_SEC)
    cap = int(config.OTP_REGISTER_RATE_LIMIT_MAX)
    with _lock:
        lst = _attempts[cid]
        cutoff = now - window
        lst[:] = [t for t in lst if t > cutoff]
        if len(lst) >= cap:
            raise HTTPException(
                status_code=429,
                detail="Too many OTP registration attempts from this client; try again later.",
            )
        lst.append(now)
