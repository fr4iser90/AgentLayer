"""SSRF guards for agent HTTP connector tools."""

from __future__ import annotations

import ipaddress
import os
import re
import socket
from urllib.parse import urlparse


_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
    }
)


def _env_domain_allowlist() -> frozenset[str] | None:
    raw = os.environ.get("AGENT_HTTP_DOMAIN_ALLOWLIST", "").strip()
    if not raw:
        return None
    parts = [p.strip().lower().strip(".") for p in raw.split(",") if p.strip()]
    return frozenset(parts) if parts else None


def _hostname_matches_allowlist(host: str, allow: frozenset[str]) -> bool:
    h = host.lower().rstrip(".")
    if not h:
        return False
    if h in allow:
        return True
    return any(h.endswith("." + d) for d in allow)


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_private
        or ip.is_unspecified
    )


def _resolve_host_ips(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return []
    return list({info[4][0] for info in infos})


def validate_outbound_url(url: str) -> tuple[bool, str]:
    """
    Return (ok, reason). Blocks loopback, link-local, private, metadata, and
    optional domain allowlist (``AGENT_HTTP_DOMAIN_ALLOWLIST``).
    """
    try:
        p = urlparse((url or "").strip())
    except Exception:
        return False, "bad_url"
    if p.scheme not in ("http", "https"):
        return False, "blocked_scheme"
    if p.username or p.password:
        return False, "blocked_credentials_in_url"
    host = (p.hostname or "").lower()
    if not host:
        return False, "blocked_scheme"
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        return False, "blocked_ssrf"
    if re.match(r"^(127\.|169\.254\.|10\.|192\.168\.)", host):
        return False, "blocked_ssrf"
    if re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host):
        return False, "blocked_ssrf"

    h = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        ip = ipaddress.ip_address(h)
        if _ip_is_blocked(ip):
            return False, "blocked_ssrf"
    except ValueError:
        for resolved in _resolve_host_ips(h):
            try:
                rip = ipaddress.ip_address(resolved)
            except ValueError:
                continue
            if _ip_is_blocked(rip):
                return False, "blocked_ssrf"

    allow = _env_domain_allowlist()
    if allow is not None and not _hostname_matches_allowlist(host, allow):
        return False, "blocked_allowlist"
    return True, ""
