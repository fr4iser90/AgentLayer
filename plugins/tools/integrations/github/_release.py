"""GitHub release JSON helpers (not a tool module)."""

from __future__ import annotations

from typing import Any


def release_summary(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data.get("id"),
        "tag_name": data.get("tag_name"),
        "name": data.get("name"),
        "draft": data.get("draft"),
        "prerelease": data.get("prerelease"),
        "html_url": data.get("html_url"),
        "target_commitish": data.get("target_commitish"),
        "published_at": data.get("published_at"),
        "created_at": data.get("created_at"),
        "author": (data.get("author") or {}).get("login"),
    }
