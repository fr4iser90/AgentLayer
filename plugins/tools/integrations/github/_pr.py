"""Pull request JSON helpers (not a tool module)."""

from __future__ import annotations

from typing import Any


def pull_request_summary(data: dict[str, Any]) -> dict[str, Any]:
    head = data.get("head") if isinstance(data.get("head"), dict) else {}
    base = data.get("base") if isinstance(data.get("base"), dict) else {}
    return {
        "number": data.get("number"),
        "title": data.get("title"),
        "state": data.get("state"),
        "draft": data.get("draft"),
        "html_url": data.get("html_url"),
        "user": (data.get("user") or {}).get("login"),
        "head_ref": head.get("ref"),
        "base_ref": base.get("ref"),
        "merged": data.get("merged"),
    }
