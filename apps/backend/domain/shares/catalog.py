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
    """The shareable types, read from the live adapter registry (step 5).

    This used to return ``[]`` under a "no fixed catalog" rule, which left
    the share UI and the agent tool with nothing true to show — they had to
    hardcode types, or show nothing. The registry is now the source, because
    the registry is what actually knows which types have an adapter that
    enforces a grant.

    Readable, not grantable. Any well-formed type id can still be stored as
    a grant (§1.4); a type absent from this list simply has no adapter, so
    granting it does nothing yet and reading it is refused. The list is
    deliberately not presented as "everything you may share" — it is
    "everything that will actually work", which is the distinction the
    pre-registry code blurred.

    Deferred import: ``registry`` imports ``canonical_resource_type`` from
    this module at load time.

    Key names follow the contract ``SharesSettings.tsx`` already codes
    against (``id`` / ``name`` / ``policy_fields``), so feeding the existing
    picker needs no frontend rename.
    """
    from apps.backend.domain.shares.registry import describe_shareable_types

    return [
        {
            "id": entry["resource_type"],
            "name": resource_type_label(entry["resource_type"], lang=lang),
            "default_identifier": entry["default_identifier"],
            "policy_fields": entry["policy_fields"],
            "listable": entry["listable"],
            "aliases": entry["aliases"],
            # Empty means the type is read live and has no shape to choose.
            # A UI that offers a projection picker should offer it only
            # where this is non-empty, rather than assuming every shareable
            # type has one.
            "projection_kinds": entry["projection_kinds"],
            "default_projection_kind": entry["default_projection_kind"],
        }
        for entry in describe_shareable_types()
    ]


def resource_type_variants(resource_type: str) -> tuple[str, ...]:
    """Canonical id only; legacy aliases handled in share_permissions_db."""
    canonical = canonical_resource_type(resource_type)
    return (canonical,) if canonical else ()
