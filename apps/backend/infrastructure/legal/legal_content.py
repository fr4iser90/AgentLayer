"""Load and render operator legal pages from DB overrides or content/legal/{jurisdiction}/ files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from apps.backend.infrastructure.settings.operator_settings import _cached_row

_REPO_ROOT = Path(__file__).resolve().parents[4]

LegalSlug = Literal["impressum", "privacy", "terms"]
LegalJurisdiction = Literal["none", "de", "en", "custom"]

_SLUG_FILE_NAMES: dict[str, dict[str, str]] = {
    "de": {
        "impressum": "impressum.md",
        "privacy": "datenschutz.md",
        "terms": "agb.md",
    },
    "en": {
        "impressum": "imprint.md",
        "privacy": "privacy.md",
        "terms": "terms.md",
    },
    "custom": {
        "impressum": "impressum.md",
        "privacy": "privacy.md",
        "terms": "terms.md",
    },
}

_SLUG_TITLES: dict[str, dict[str, str]] = {
    "de": {
        "impressum": "Impressum",
        "privacy": "Datenschutzerklärung",
        "terms": "Allgemeine Geschäftsbedingungen",
    },
    "en": {
        "impressum": "Legal notice",
        "privacy": "Privacy policy",
        "terms": "Terms of service",
    },
    "custom": {
        "impressum": "Legal notice",
        "privacy": "Privacy policy",
        "terms": "Terms of service",
    },
}

_OVERRIDE_KEYS: dict[LegalSlug, str] = {
    "impressum": "legal_impressum_md",
    "privacy": "legal_privacy_md",
    "terms": "legal_terms_md",
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*legal_entity\.(\w+)\s*\}\}")


def _normalize_jurisdiction(raw: Any) -> LegalJurisdiction:
    v = str(raw or "none").strip().lower()
    return v if v in ("none", "de", "en", "custom") else "none"


def legal_settings() -> dict[str, Any]:
    row = _cached_row()
    jurisdiction = _normalize_jurisdiction(row.get("legal_jurisdiction"))
    return {
        "enabled": bool(row.get("legal_enabled")) and jurisdiction != "none",
        "jurisdiction": jurisdiction,
        "terms_enabled": bool(row.get("legal_terms_enabled")),
        "entity": {
            "name": (str(row.get("legal_entity_name") or "").strip())[:256],
            "address": (str(row.get("legal_entity_address") or "").strip()),
            "email": (str(row.get("legal_entity_email") or "").strip())[:256],
            "phone": (str(row.get("legal_entity_phone") or "").strip())[:64],
        },
        "overrides": {
            "impressum": row.get("legal_impressum_md"),
            "privacy": row.get("legal_privacy_md"),
            "terms": row.get("legal_terms_md"),
        },
    }


def _substitute_entity_placeholders(text: str, entity: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return entity.get(key, "")

    return _PLACEHOLDER_RE.sub(repl, text)


def _legal_content_dir(jurisdiction: LegalJurisdiction) -> Path:
    return _REPO_ROOT / "content" / "legal" / jurisdiction


def _read_file_markdown(jurisdiction: LegalJurisdiction, slug: LegalSlug) -> str | None:
    file_names = _SLUG_FILE_NAMES.get(jurisdiction) or _SLUG_FILE_NAMES["en"]
    file_name = file_names.get(slug)
    if not file_name:
        return None
    path = _legal_content_dir(jurisdiction) / file_name
    if not path.is_file():
        if jurisdiction == "custom":
            path = _legal_content_dir("de") / (_SLUG_FILE_NAMES["de"].get(slug) or file_name)
            if not path.is_file():
                path = _legal_content_dir("en") / file_name
        if not path.is_file():
            return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def legal_page_title(slug: LegalSlug, jurisdiction: LegalJurisdiction | None = None) -> str:
    j = jurisdiction or _normalize_jurisdiction(_cached_row().get("legal_jurisdiction"))
    titles = _SLUG_TITLES.get(j) or _SLUG_TITLES["en"]
    return titles.get(slug, slug)


def legal_page_body_md(slug: LegalSlug) -> str | None:
    settings = legal_settings()
    if not settings["enabled"]:
        return None
    jurisdiction: LegalJurisdiction = settings["jurisdiction"]
    if slug == "terms" and not settings["terms_enabled"]:
        return None

    override = settings["overrides"].get(slug)
    if isinstance(override, str) and override.strip():
        raw = override.strip()
    else:
        raw = _read_file_markdown(jurisdiction, slug)
        if raw is None and jurisdiction != "en":
            raw = _read_file_markdown("en", slug)
    if raw is None:
        return None
    return _substitute_entity_placeholders(raw, settings["entity"])


def legal_public_pages() -> list[dict[str, str]]:
    settings = legal_settings()
    if not settings["enabled"]:
        return []
    jurisdiction: LegalJurisdiction = settings["jurisdiction"]
    slugs: list[LegalSlug] = ["impressum", "privacy"]
    if settings["terms_enabled"]:
        slugs.append("terms")
    pages: list[dict[str, str]] = []
    for slug in slugs:
        if legal_page_body_md(slug) is None:
            continue
        pages.append(
            {
                "slug": slug,
                "title": legal_page_title(slug, jurisdiction),
                "href": f"/app/legal/{slug}",
            }
        )
    return pages


def legal_public_index() -> dict[str, Any]:
    settings = legal_settings()
    return {
        "enabled": settings["enabled"],
        "jurisdiction": settings["jurisdiction"],
        "terms_enabled": settings["terms_enabled"],
        "pages": legal_public_pages(),
    }
