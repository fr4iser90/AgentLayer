"""Shared GitHub REST client (not scanned as a tool module)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from apps.backend.infrastructure.db import db
from apps.backend.domain.identity import get_identity

GITHUB_API = "https://api.github.com"
USER_SECRET_KEY = "github_pat"
HTTP_TIMEOUT = 30.0
MAX_SEARCH_ITEMS = 20
MAX_FILE_CHARS = 120_000
MAX_ISSUE_BODY_CHARS = 24_000

TOOL_USER_SECRET_FORMS: dict[str, dict[str, Any]] = {
    USER_SECRET_KEY: {
        "title": "GitHub token",
        "help": (
            "Fine-grained or classic **Personal Access Token** (`ghp_…` / `github_pat_…`). "
            "You can paste the token alone, or use the field below (saved as JSON for the tool reader)."
        ),
        "fields": [
            {"name": "token", "label": "Personal access token", "type": "password", "required": True},
        ],
    }
}


def is_error_payload(status: int, data: Any) -> bool:
    if status == 0:
        return True
    return isinstance(data, dict) and data.get("ok") is False


def _parse_user_pat(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return s
    if isinstance(obj, dict):
        return str(obj.get("token") or obj.get("pat") or "").strip()
    return s


def _token() -> str | None:
    _tid, uid = get_identity()
    if uid is not None:
        raw = db.user_secret_get_plaintext(uid, USER_SECRET_KEY)
        if raw:
            t = _parse_user_pat(raw)
            if t:
                return t
    env_t = os.environ.get("GITHUB_TOKEN", "").strip()
    return env_t or None


def _headers(tok: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {tok}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "jetpack-agent-layer-github-tool",
    }


def github_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    tok = _token()
    if not tok:
        return (
            0,
            {
                "ok": False,
                "error": (
                    "No GitHub token: set GITHUB_TOKEN in the agent environment (e.g. docker/.env) "
                    f"or register a user secret `{USER_SECRET_KEY}` via register_secrets "
                    '(JSON {"token":"ghp_…"} or github_pat_… string).'
                ),
            },
        )
    url = f"{GITHUB_API}{path}"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.request(
                method,
                url,
                headers=_headers(tok),
                params=params,
                json=json_body,
            )
    except httpx.HTTPError as e:
        return 0, {"ok": False, "error": f"http error: {e}"}
    try:
        data = r.json() if r.content else None
    except json.JSONDecodeError:
        data = {"raw": r.text[:2000]}
    if r.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            msg = data.get("message")
        return r.status_code, {
            "ok": False,
            "status": r.status_code,
            "error": msg or r.reason_phrase or "request failed",
            "github": data if isinstance(data, dict) else str(data)[:500],
        }
    return r.status_code, data
