"""Share resource type normalization — no hardcoded catalog of allowed types."""

from __future__ import annotations

import re
from typing import Any

# Lowercase id: letters, digits, underscore, dot, hyphen (2–50 chars).
_RESOURCE_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,48}$")


def canonical_resource_type(resource_type: str) -> str | None:
    """Normalize a free-form resource type id, or None when empty/invalid."""
    key = (resource_type or "").strip().lower().replace(" ", "_")
    if not key or not _RESOURCE_TYPE_RE.match(key):
        return None
    return key


def resource_type_label(resource_type: str, *, lang: str = "en") -> str:
    _ = lang
    c = canonical_resource_type(resource_type) or (resource_type or "").strip()
    if not c:
        return "unknown"
    return c.replace("_", " ").replace("-", " ")


def catalog_for_api(*, lang: str = "en") -> list[dict[str, Any]]:
    """No fixed catalog — callers use live grants or any resource_type string."""
    _ = lang
    return []


def resource_type_variants(resource_type: str) -> tuple[str, ...]:
    """Canonical id only; legacy aliases handled in share_permissions_db."""
    canonical = canonical_resource_type(resource_type)
    return (canonical,) if canonical else ()
