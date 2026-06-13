"""List GitHub repositories for the signed-in user (REST API)."""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from plugins.tools.integrations.github.lib.auth import USER_SECRET_KEY, github_pat_for_user_id

GITHUB_API = "https://api.github.com"
HTTP_TIMEOUT = 30.0
MAX_PER_PAGE = 100


def _headers(tok: str) -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {tok}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "agentlayer-github-api",
    }


def list_user_repos(
    user_id: uuid.UUID,
    *,
    page: int = 1,
    per_page: int = 100,
    affiliation: str = "owner,organization_member",
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Return slim repo rows and optional error message.

    Uses **only** the authenticated user's ``github_pat`` secret — no shared ``GITHUB_TOKEN``
    fallback (multi-user safe).

    Each row: ``full_name``, ``name``, ``html_url``, ``clone_url``, ``default_branch``,
    ``description``, ``private``, ``updated_at``.
    """
    tok = github_pat_for_user_id(user_id)
    if not tok:
        return [], (
            f"No GitHub token for this user. Save `{USER_SECRET_KEY}` in "
            "Settings → Connections (per-user secret; not a shared server token)."
        )

    pg = max(1, min(20, int(page)))
    lim = max(1, min(MAX_PER_PAGE, int(per_page)))
    params = {
        "affiliation": affiliation,
        "sort": "updated",
        "direction": "desc",
        "per_page": lim,
        "page": pg,
    }
    url = f"{GITHUB_API}/user/repos"
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            r = client.get(url, headers=_headers(tok), params=params)
    except httpx.HTTPError as e:
        return [], f"GitHub request failed: {e}"

    try:
        data = r.json() if r.content else []
    except Exception:
        data = []

    if r.status_code >= 400:
        msg = None
        if isinstance(data, dict):
            msg = data.get("message")
        return [], msg or r.reason_phrase or f"GitHub HTTP {r.status_code}"

    if not isinstance(data, list):
        return [], "Unexpected GitHub response"

    out: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        full_name = str(item.get("full_name") or "").strip()
        if not full_name:
            continue
        clone_url = str(item.get("clone_url") or "").strip()
        if not clone_url:
            continue
        out.append(
            {
                "full_name": full_name,
                "name": str(item.get("name") or full_name.split("/")[-1]),
                "html_url": str(item.get("html_url") or "").strip(),
                "clone_url": clone_url,
                "default_branch": str(item.get("default_branch") or "main").strip() or "main",
                "description": str(item.get("description") or "").strip(),
                "private": bool(item.get("private")),
                "updated_at": item.get("updated_at"),
            }
        )
    return out, None
