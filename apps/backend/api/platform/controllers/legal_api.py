"""Public legal pages (Impressum, privacy, terms) — no authentication required."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException

from apps.backend.infrastructure.legal.legal_content import (
    legal_page_body_md,
    legal_page_title,
    legal_public_index,
    legal_settings,
)

router = APIRouter()

LegalSlugParam = Literal["impressum", "privacy", "terms"]


@router.get("/v1/public/legal")
async def public_legal_index():
    return legal_public_index()


@router.get("/v1/public/legal/{slug}")
async def public_legal_page(slug: LegalSlugParam):
    settings = legal_settings()
    if not settings["enabled"]:
        raise HTTPException(status_code=404, detail="legal_not_enabled")
    if slug == "terms" and not settings["terms_enabled"]:
        raise HTTPException(status_code=404, detail="legal_terms_not_enabled")
    body_md = legal_page_body_md(slug)
    if body_md is None:
        raise HTTPException(status_code=404, detail="legal_page_not_found")
    return {
        "slug": slug,
        "title": legal_page_title(slug),
        "body_md": body_md,
    }
