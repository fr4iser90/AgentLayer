"""Display defaults per package id (category, names, order, taglines) — icons live in :mod:`tool_ui_icons`."""

from __future__ import annotations

from typing import Any

PACKAGE_UI_DEFAULTS: dict[str, dict[str, Any]] = {
    "gmail": {
        "category": "productivity",
        "display_name": "Gmail",
        "order": 10,
        "tagline": "Search, read, and summarize mail",
    },
    "todos": {
        "category": "productivity",
        "display_name": "Todos",
        "order": 20,
    },
    "todo": {
        "category": "productivity",
        "display_name": "Task list",
        "order": 21,
        "tagline": "List, read, and add tasks on kind=todo dashboards",
    },
    "calendar_ics": {
        "category": "productivity",
        "display_name": "Calendar",
        "order": 30,
    },
    "shopping_list": {
        "category": "productivity",
        "display_name": "Shopping list",
        "order": 25,
        "tagline": "List, read, and add items on shopping_list dashboards",
    },
    "pets": {
        "category": "productivity",
        "display_name": "Pets",
        "order": 26,
        "tagline": "Read and update pets dashboards (animals, notes, album photos)",
    },
    "ideas": {
        "category": "productivity",
        "display_name": "Ideas & memos",
        "order": 27,
        "tagline": "Read and update ideas dashboards (idea table + scratchpad)",
    },
    "clock": {
        "category": "productivity",
        "display_name": "Clock",
        "order": 40,
    },
    "kb": {
        "category": "knowledge",
        "display_name": "Knowledge Base",
        "order": 10,
    },
    "rag": {
        "category": "knowledge",
        "display_name": "Knowledge Search",
        "order": 20,
        "tagline": "Semantic search over ingested documents",
    },
    "web_search": {
        "category": "knowledge",
        "display_name": "Web Search",
        "order": 30,
    },
    "github": {
        "category": "developer",
        "display_name": "GitHub",
        "order": 10,
    },
    "local_files": {
        "category": "developer",
        "display_name": "Local Files",
        "order": 20,
    },
    "create_tool": {
        "category": "developer",
        "display_name": "Create Tool",
        "order": 30,
    },
    "list_tools": {
        "category": "developer",
        "display_name": "List Tools",
        "order": 31,
    },
    "read_tool": {
        "category": "developer",
        "display_name": "Read Tool",
        "order": 32,
    },
    "update_tool": {
        "category": "developer",
        "display_name": "Update Tool",
        "order": 33,
    },
    "replace_tool": {
        "category": "developer",
        "display_name": "Replace Tool",
        "order": 34,
    },
    "rename_tool": {
        "category": "developer",
        "display_name": "Rename Tool",
        "order": 35,
    },
    "run_iterative_html_build": {
        "category": "developer",
        "display_name": "HTML Builder",
        "order": 40,
        "tagline": "Iterative HTML workflows",
    },
    "tool_help": {
        "category": "developer",
        "display_name": "Tool Help",
        "order": 50,
    },
    "inpainting_realvision": {
        "category": "creative",
        "display_name": "Image Editor",
        "order": 10,
    },
    "openweather": {
        "category": "outdoor",
        "display_name": "Weather",
        "order": 5,
    },
    "outdoor_snapshot": {
        "category": "outdoor",
        "display_name": "Outdoor Snapshot",
        "order": 8,
        "tagline": "Time, optional weather, daylight context",
    },
    "fishing_bait": {
        "category": "outdoor",
        "display_name": "Fishing — Bait",
        "order": 20,
    },
    "fishing_bite_index": {
        "category": "outdoor",
        "display_name": "Fishing — Bite index",
        "order": 21,
    },
    "fishing_spot": {
        "category": "outdoor",
        "display_name": "Fishing — Spots",
        "order": 22,
    },
    "hunting_tracking": {
        "category": "outdoor",
        "display_name": "Hunting — Tracking",
        "order": 30,
    },
    "hunting_wind": {
        "category": "outdoor",
        "display_name": "Hunting — Wind",
        "order": 31,
    },
    "survival_risk": {
        "category": "outdoor",
        "display_name": "Survival — Risk",
        "order": 40,
    },
    "survival_shelter": {
        "category": "outdoor",
        "display_name": "Survival — Shelter",
        "order": 41,
    },
    "survival_water": {
        "category": "outdoor",
        "display_name": "Survival — Water",
        "order": 42,
    },
    "register_secrets": {
        "category": "system",
        "display_name": "Register secrets",
        "order": 10,
    },
    "save_user_secret": {
        "category": "system",
        "display_name": "Save user secret",
        "order": 10,
    },
    "request_user_secret": {
        "category": "system",
        "display_name": "Request user secret",
        "order": 10,
    },
    "secrets_help": {
        "category": "system",
        "display_name": "Secrets help",
        "order": 11,
    },
    "echo": {
        "category": "system",
        "display_name": "Echo (demo)",
        "order": 90,
    },
}
