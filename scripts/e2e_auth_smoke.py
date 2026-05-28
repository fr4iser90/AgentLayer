#!/usr/bin/env python3
"""Authenticated smoke test against running Agent Layer (loads .env, never prints secrets)."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "apps" / "frontend"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _cred() -> tuple[str, str]:
    email = (
        os.environ.get("AGENT_E2E_EMAIL")
        or os.environ.get("AGENT_TEST_EMAIL")
        or os.environ.get("AGENT_INITIAL_ADMIN_EMAIL")
        or ""
    ).strip()
    password = (
        os.environ.get("AGENT_E2E_PASSWORD")
        or os.environ.get("AGENT_TEST_PASSWORD")
        or os.environ.get("AGENT_INITIAL_ADMIN_PASSWORD")
        or ""
    ).strip()
    if not email or not password:
        raise SystemExit(
            "missing login credentials in environment "
            "(set AGENT_INITIAL_ADMIN_EMAIL/PASSWORD or AGENT_E2E_EMAIL/PASSWORD in .env)"
        )
    return email, password


def _base() -> str:
    port = (os.environ.get("AGENT_HTTP_PORT") or "8088").strip()
    return f"http://127.0.0.1:{port}"


def _opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _routes() -> list[str]:
    manifest = (FRONTEND / "scripts" / "routes-manifest.mjs").read_text(encoding="utf-8")
    return re.findall(r'path: "(/app[^"]*)"', manifest)


def _api_checks(role: str) -> list[tuple[str, str]]:
    common = [
        ("GET", "/auth/me"),
        ("GET", "/auth/setup-status"),
        ("GET", "/v1/user/conversations"),
        ("GET", "/v1/workspaces"),
        ("GET", "/v1/dashboards"),
        ("GET", "/v1/tools"),
        ("GET", "/v1/tasks"),
        ("GET", "/v1/user/profile"),
    ]
    admin = [
        ("GET", "/v1/admin/operator-settings"),
        ("GET", "/v1/admin/users"),
        ("GET", "/v1/admin/tools"),
        ("GET", "/v1/admin/interfaces"),
    ]
    return common + (admin if role == "admin" else [])


def main() -> int:
    _load_dotenv(REPO / ".env")
    _load_dotenv(REPO / ".env.e2e")
    email, password = _cred()
    base = _base()
    opener = _opener()

    login_body = json.dumps({"email": email, "password": password}).encode()
    login_req = urllib.request.Request(
        f"{base}/auth/login",
        data=login_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener.open(login_req, timeout=30) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"LOGIN FAILED: HTTP {e.code}")
        return 1

    token = payload.get("access_token")
    user = payload.get("user") or {}
    role = user.get("role") or "?"
    user_id = user.get("id") or "?"
    print(f"LOGIN OK: role={role} user_id={user_id}")

    failures: list[str] = []

    for path in _routes():
        if path in ("/app/login", "/app/setup"):
            continue
        req = urllib.request.Request(f"{base}{path}")
        try:
            with opener.open(req, timeout=20) as resp:
                code = resp.status
                html = resp.read(800).decode(errors="ignore")
        except urllib.error.HTTPError as e:
            code = e.code
            html = ""
        if code != 200:
            failures.append(f"SPA {path} -> {code}")
        elif "index-" not in html and "<!DOCTYPE html>" in html:
            failures.append(f"SPA {path} -> 200 but missing bundle ref")

    headers = {"Authorization": f"Bearer {token}"}
    for method, path in _api_checks(role):
        req = urllib.request.Request(f"{base}{path}", headers=headers, method=method)
        try:
            with opener.open(req, timeout=30) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        if code not in (200, 204):
            failures.append(f"API {method} {path} -> {code}")

    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    n_routes = len([p for p in _routes() if p not in ("/app/login", "/app/setup")])
    n_api = len(_api_checks(role))
    print(f"ALL OK: {n_routes} SPA routes + {n_api} API endpoints (authenticated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
