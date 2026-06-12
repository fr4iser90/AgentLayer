"""OSV.dev vulnerability lookups with a small in-process TTL cache."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

OSV_API_URL = "https://api.osv.dev/v1/query"
_CACHE: dict[tuple[str, str, str], tuple[float, list["OsvFinding"]]] = {}
_CACHE_TTL_SEC = 24 * 3600


@dataclass(frozen=True)
class OsvFinding:
    id: str
    severity: str
    summary: str = ""


def _normalize_severity(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip().upper()
    if isinstance(raw, (int, float)):
        score = float(raw)
        if score >= 9.0:
            return "CRITICAL"
        if score >= 7.0:
            return "HIGH"
        if score >= 4.0:
            return "MEDIUM"
        return "LOW"
    return "UNKNOWN"


def _severity_from_vuln(vuln: dict[str, Any]) -> str:
    db = vuln.get("database_specific")
    if isinstance(db, dict):
        sev = db.get("severity")
        if isinstance(sev, str) and sev.strip():
            return sev.strip().upper()
    for item in vuln.get("severity") or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("score"), (str, int, float)):
            try:
                return _normalize_severity(float(item["score"]))
            except (TypeError, ValueError):
                pass
    return "UNKNOWN"


def _ecosystem_for_osv(ecosystem: str) -> str:
    if ecosystem == "pypi":
        return "PyPI"
    if ecosystem == "npm":
        return "npm"
    return ecosystem


def clear_osv_cache() -> None:
    _CACHE.clear()


def query_vulnerabilities(
    *,
    ecosystem: str,
    name: str,
    version: str | None,
    timeout_sec: float = 8.0,
) -> tuple[list[OsvFinding], str | None]:
    """
    Return (findings, error). ``error`` is set when the HTTP call fails.
    """
    eco = ecosystem.lower()
    pkg = name.strip()
    ver = (version or "").strip()
    cache_key = (eco, pkg.lower(), ver or "*")
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < _CACHE_TTL_SEC:
        return list(cached[1]), None

    body: dict[str, Any] = {
        "package": {"name": pkg, "ecosystem": _ecosystem_for_osv(eco)},
    }
    if ver:
        body["version"] = ver

    try:
        with httpx.Client(timeout=timeout_sec) as client:
            resp = client.post(OSV_API_URL, json=body)
    except httpx.HTTPError as exc:
        logger.warning("package_admission osv lookup failed for %s: %s", pkg, exc)
        return [], f"osv lookup failed: {exc}"

    if resp.status_code >= 400:
        msg = f"osv http {resp.status_code}"
        logger.warning("package_admission osv lookup failed for %s: %s", pkg, msg)
        return [], msg

    try:
        data = resp.json()
    except ValueError:
        return [], "osv invalid json"

    findings: list[OsvFinding] = []
    for vuln in data.get("vulns") or []:
        if not isinstance(vuln, dict):
            continue
        vid = str(vuln.get("id") or "").strip() or "unknown"
        findings.append(
            OsvFinding(
                id=vid,
                severity=_severity_from_vuln(vuln),
                summary=str(vuln.get("summary") or "")[:300],
            )
        )

    _CACHE[cache_key] = (now, findings)
    return findings, None
