"""Load share resource catalog (labels, policy fields, aliases)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CATALOG_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "share_resource_catalog.json"
)


@lru_cache(maxsize=1)
def share_catalog_raw() -> dict[str, Any]:
    if not _CATALOG_PATH.is_file():
        return {"version": 1, "resources": []}
    with _CATALOG_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {"version": 1, "resources": []}


def share_catalog_resources() -> list[dict[str, Any]]:
    raw = share_catalog_raw()
    items = raw.get("resources")
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict) and item.get("id"):
            out.append(dict(item))
    return out


def _alias_map() -> dict[str, str]:
    m: dict[str, str] = {}
    for res in share_catalog_resources():
        rid = str(res.get("id") or "").strip().lower()
        if not rid:
            continue
        m[rid] = rid
        for alias in res.get("aliases") or []:
            key = str(alias).strip().lower()
            if key:
                m[key] = rid
    return m


def canonical_resource_type(resource_type: str) -> str | None:
    key = (resource_type or "").strip().lower()
    if not key:
        return None
    aliases = _alias_map()
    if key in aliases:
        return aliases[key]
    known = {str(r.get("id") or "").lower() for r in share_catalog_resources()}
    return key if key in known else None


def resource_catalog_entry(resource_type: str) -> dict[str, Any] | None:
    canonical = canonical_resource_type(resource_type)
    if not canonical:
        return None
    for res in share_catalog_resources():
        if str(res.get("id") or "").lower() == canonical:
            return res
    return None


def resource_type_label(resource_type: str, *, lang: str = "en") -> str:
    entry = resource_catalog_entry(resource_type)
    if entry:
        labels = entry.get("label") or {}
        if isinstance(labels, dict):
            label = labels.get(lang) or labels.get("en")
            if label:
                return str(label)
        return str(entry.get("id") or resource_type)
    return (resource_type or "unknown").strip() or "unknown"


def catalog_for_api(*, lang: str = "en") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for res in share_catalog_resources():
        labels = res.get("label") if isinstance(res.get("label"), dict) else {}
        out.append(
            {
                "id": res.get("id"),
                "icon": res.get("icon") or "",
                "name": labels.get(lang) or labels.get("en") or res.get("id"),
                "default_identifier": res.get("default_identifier") or "primary",
                "policy_fields": list(res.get("policy_fields") or []),
            }
        )
    return out


def resource_type_variants(resource_type: str) -> tuple[str, ...]:
    """Canonical id plus catalog aliases for DB lookup."""
    canonical = canonical_resource_type(resource_type) or (resource_type or "").strip().lower()
    if not canonical:
        return ()
    entry = resource_catalog_entry(canonical)
    aliases = list(entry.get("aliases") or []) if entry else []
    out: list[str] = []
    for candidate in (canonical, *aliases):
        key = str(candidate).strip().lower()
        if key and key not in out:
            out.append(key)
    return tuple(out)
