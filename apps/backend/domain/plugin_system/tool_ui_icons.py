"""
Icon hints (lucide-style names) per package id — separate from :mod:`tool_ui_defaults`
so lists stay readable as the catalog grows.
"""

from __future__ import annotations

ICON_MAP: dict[str, str] = {
    "gmail": "mail",
    "todo": "list-checks",
    "todos": "list-checks",
    "calendar_ics": "calendar",
    "shopping_list": "shopping-cart",
    "pets": "paw-print",
    "ideas": "lightbulb",
    "clock": "clock",
    "kb": "notebook-pen",
    "rag": "search",
    "memory": "brain",
    "memory_graph": "share-2",
    "web_search": "globe",
    "github": "github",
    "local_files": "folder-open",
    "create_tool": "plus-square",
    "list_tools": "list",
    "read_tool": "file-code",
    "update_tool": "file-edit",
    "replace_tool": "file-input",
    "rename_tool": "file-signature",
    "run_iterative_html_build": "layout-template",
    "tool_help": "circle-help",
    "inpainting_realvision": "image",
    "openweather": "cloud-sun",
    "outdoor_snapshot": "compass",
    "fishing_bait": "fish",
    "fishing_bite_index": "fish",
    "fishing_spot": "map-pin",
    "hunting_tracking": "footprints",
    "hunting_wind": "wind",
    "survival_risk": "alert-triangle",
    "survival_shelter": "tent",
    "survival_water": "droplets",
    "register_secrets": "key-round",
    "request_user_secret": "key-round",
    "save_user_secret": "key-round",
    "secrets_help": "book-open",
    "echo": "message-circle",
}
