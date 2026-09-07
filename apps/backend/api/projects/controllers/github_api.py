"""GitHub integration HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from plugins.tools.integrations.github.lib.repos import list_user_repos
from apps.backend.application.identity.use_cases.request_auth import get_current_user

router = APIRouter(prefix="/v1/integrations/github", tags=["integrations", "github"])


@router.get("/repos")
async def github_list_repos(
    request: Request,
    page: int = Query(default=1, ge=1, le=20),
    per_page: int = Query(default=100, ge=1, le=100),
):
    """List repositories visible to the authenticated user (requires per-user github_pat)."""
    user = await get_current_user(request)
    repos, err = list_user_repos(user.id, page=page, per_page=per_page)
    if err and not repos:
        raise HTTPException(status_code=400, detail=err)
    return {
        "ok": True,
        "repos": repos,
        "page": page,
        "per_page": per_page,
        "count": len(repos),
        "warning": err,
    }
