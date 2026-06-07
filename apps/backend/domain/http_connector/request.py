"""Execute outbound HTTP requests for connector tools."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from apps.backend.domain.http_connector.auth import resolve_auth
from apps.backend.domain.http_connector.extract import extract_path
from apps.backend.domain.http_connector.ssrf import validate_outbound_url


def _timeout() -> float:
    try:
        return max(3.0, float(os.environ.get("AGENT_HTTP_CONNECTOR_TIMEOUT", "30")))
    except ValueError:
        return 30.0


def _max_response_bytes() -> int:
    try:
        return max(10_000, int(os.environ.get("AGENT_HTTP_CONNECTOR_MAX_RESPONSE_BYTES", "500000")))
    except ValueError:
        return 500_000


def build_request_url(
    *,
    url: str | None = None,
    base_url: str | None = None,
    path: str | None = None,
    query: dict[str, str] | None = None,
) -> str:
    u = (url or "").strip()
    base = (base_url or "").strip()
    p = (path or "").strip()
    if u.startswith("http://") or u.startswith("https://"):
        full = u
    elif p.startswith("http://") or p.startswith("https://"):
        full = p
    elif base and p:
        full = urljoin(base.rstrip("/") + "/", p.lstrip("/"))
    elif base:
        full = base.rstrip("/")
    elif u:
        full = u
    elif p:
        full = p
    else:
        return ""
    q = query or {}
    if q:
        sep = "&" if "?" in full else "?"
        full = f"{full}{sep}{urlencode(q)}"
    return full


def _normalize_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if key:
            out[key] = str(v)
    return out


def _normalize_query(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if str(k).strip()}


def execute_http(
    *,
    user_id: Any,
    method: str,
    url: str | None = None,
    base_url: str | None = None,
    path: str | None = None,
    query: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    body: Any = None,
    auth: dict[str, Any] | None = None,
    extract: str | None = None,
) -> dict[str, Any]:
    """Run one HTTP call. Returns a JSON-serializable dict (secrets never included)."""
    import uuid as _uuid

    uid = user_id if isinstance(user_id, _uuid.UUID) else _uuid.UUID(str(user_id))
    m = (method or "GET").strip().upper()
    if m not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"):
        return {"ok": False, "error": f"unsupported method {m!r}"}

    q = _normalize_query(query)
    hdrs = _normalize_headers(headers)

    auth_hdrs, auth_q, auth_err = resolve_auth(uid, auth if isinstance(auth, dict) else None)
    if auth_err:
        return {"ok": False, "error": auth_err}
    hdrs = {**hdrs, **auth_hdrs}
    q = {**auth_q, **q}

    full_url = build_request_url(url=url, base_url=base_url, path=path, query=q)
    if not full_url:
        return {"ok": False, "error": "url or base_url+path required"}

    ok, why = validate_outbound_url(full_url)
    if not ok:
        return {"ok": False, "error": why, "url": urlparse(full_url)._replace(fragment="").geturl()}

    json_body: Any = None
    data_body: str | bytes | None = None
    if body is not None and m not in ("GET", "HEAD"):
        if isinstance(body, (dict, list)):
            json_body = body
            if "Content-Type" not in {k.title(): v for k, v in hdrs.items()}:
                hdrs.setdefault("Content-Type", "application/json")
        else:
            data_body = str(body)

    max_bytes = _max_response_bytes()
    try:
        with httpx.Client(timeout=_timeout(), trust_env=False, follow_redirects=True) as client:
            r = client.request(
                m,
                full_url,
                headers=hdrs,
                json=json_body,
                content=data_body.encode("utf-8") if isinstance(data_body, str) else data_body,
            )
    except httpx.HTTPError as e:
        return {"ok": False, "error": f"http error: {e}", "url": full_url}

    content = r.content[:max_bytes]
    truncated = len(r.content) > max_bytes
    parsed: Any
    ctype = (r.headers.get("content-type") or "").lower()
    if "json" in ctype or content[:1] in (b"{", b"["):
        try:
            parsed = json.loads(content.decode("utf-8", errors="replace") or "null")
        except json.JSONDecodeError:
            parsed = {"raw": content.decode("utf-8", errors="replace")[:8000]}
    else:
        text = content.decode("utf-8", errors="replace")
        parsed = {"raw": text[:8000]}

    out: dict[str, Any] = {
        "ok": r.status_code < 400,
        "status": r.status_code,
        "url": str(r.url),
        "response": parsed,
    }
    if truncated:
        out["truncated"] = True
    if r.status_code >= 400:
        msg = None
        if isinstance(parsed, dict):
            msg = parsed.get("error") or parsed.get("message") or parsed.get("detail")
        out["error"] = msg or r.reason_phrase or "request failed"
    if extract:
        out["extracted"] = extract_path(parsed, extract)
    return out
