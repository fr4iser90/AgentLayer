"""Shared dashboard API request models and helpers."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from apps.backend.application.dashboards.use_cases.dashboard_controller_services import public_share
from apps.backend.application.dashboards.use_cases.dashboard_controller_services import dashboard_tables_exist


def require_dashboard_schema() -> None:
    if not dashboard_tables_exist():
        raise HTTPException(
            status_code=400,
            detail="dashboard schema not installed; use POST /v1/dashboards/install from the UI first",
        )


class DashboardCreateBody(BaseModel):
    kind: str = Field(default="custom", max_length=64)
    template_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=500)
    ui_layout: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


class DashboardPatchBody(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    ui_layout: dict[str, Any] | None = None
    data: dict[str, Any] | None = None


class DashboardMemberAddBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    role: str = Field(default="viewer", max_length=16)


class DashboardBlockShareBody(BaseModel):
    """Share only specific layout block ids; ``view`` = read-only, ``edit`` = patch those blocks."""

    email: str = Field(..., min_length=3, max_length=254)
    block_ids: list[str] = Field(default_factory=list)
    permission: str = Field(default="view", max_length=8)


class DashboardPublicShareCreateBody(BaseModel):
    """Create a public read-only link. Empty ``block_ids`` = entire dashboard."""

    block_ids: list[str] = Field(default_factory=list)
    label: str = Field(default="", max_length=200)
    expires_at: str | None = Field(
        default=None,
        description="Optional ISO-8601 expiry (UTC). Omit for no expiry.",
    )
    password: str | None = Field(
        default=None,
        max_length=128,
        description="Optional link password (min 4 chars). Omit for open links.",
    )


class DashboardInstallBody(BaseModel):
    """Which bundle kinds to apply ``schema_sql`` for (nothing runs until you pick)."""

    kinds: list[str] = Field(default_factory=list)


class DashboardFromTemplateBody(BaseModel):
    kind: str = Field(default="custom", max_length=64)
    template_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=500)
    ui_layout: dict[str, Any] = Field(default_factory=dict)
    initial_data: dict[str, Any] | None = Field(default=None)


class DashboardPinBlockBody(BaseModel):
    source_dashboard_id: str = Field(..., min_length=36, max_length=36)
    source_block_id: str = Field(..., min_length=1, max_length=120)
    parent_block_id: str | None = Field(default=None, max_length=120)
    title: str | None = Field(default=None, max_length=200)


def share_password_from_request(request: Request) -> str | None:
    raw = (request.headers.get(public_share.SHARE_PASSWORD_HEADER) or "").strip()
    return raw or None


def preferred_lang(request: Request) -> str:
    raw = (request.headers.get("accept-language") or "").strip().lower()
    if raw.startswith("de") or ",de" in raw:
        return "de"
    return "en"
