"""Category taxonomy and domain fallbacks for :mod:`tool_ui_catalog`."""

from __future__ import annotations

# Order of sections in Settings → Tools and API consumers.
UI_CATEGORY_ORDER: tuple[str, ...] = (
    "productivity",
    "knowledge",
    "developer",
    "creative",
    "outdoor",
    "system",
)

UI_CATEGORY_LABEL: dict[str, str] = {
    "productivity": "Productivity",
    "knowledge": "Knowledge",
    "developer": "Developer",
    "creative": "Creative",
    "outdoor": "Outdoor",
    "system": "System & Admin",
}

VALID_UI_CATEGORIES: frozenset[str] = frozenset(UI_CATEGORY_ORDER)

# When package id has no row in package defaults, map TOOL_DOMAIN (or id) → category slug.
DOMAIN_CATEGORY_FALLBACK: dict[str, str] = {
    "mail": "productivity",
    "gmail": "productivity",
    "productivity": "productivity",
    "calendar": "productivity",
    "shopping": "productivity",
    "pets": "productivity",
    "ideas": "productivity",
    "tasks": "productivity",
    "todos": "productivity",
    "clocks": "productivity",
    "kb": "knowledge",
    "knowledge": "knowledge",
    "rag": "knowledge",
    "web_search": "knowledge",
    "github": "developer",
    "repository": "developer",
    "workspace": "developer",
    "files": "developer",
    "meta": "system",
    "tool_factory": "developer",
    "creative": "creative",
    "image_editor": "creative",
    "weather": "outdoor",
    "fishing": "outdoor",
    "hunting": "outdoor",
    "survival": "outdoor",
    "shared": "outdoor",
    "secrets": "system",
    "platform": "system",
    "delegate": "system",
    "operator": "system",
    "outdoor": "outdoor",
}


def prettify_package_id(pid: str) -> str:
    s = (pid or "").strip().replace("_", " ").strip()
    if not s:
        return "Package"
    return s[:1].upper() + s[1:]
