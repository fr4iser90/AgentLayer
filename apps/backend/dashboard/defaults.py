"""Default ``ui_layout`` / ``data`` per ``kind`` — paths come from ``dashboard/**/dashboard.kind.json``."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from apps.backend.dashboard.bundle import template_path_for_kind, template_path_for_template_id

_CUSTOM_UI: dict[str, Any] = {
    "version": 1,
    "blocks": [
        {
            "id": "note",
            "type": "markdown",
            "grid": {"x": 0, "y": 0, "w": 12, "h": 12},
            "props": {"dataPath": "notes", "placeholder": "Notizen…"},
        }
    ],
}
_CUSTOM_DATA: dict[str, Any] = {"notes": ""}


def _load_kind_template(path: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    ui = raw.get("ui_layout")
    data = raw.get("initial_data")
    if isinstance(ui, dict) and isinstance(data, dict):
        return copy.deepcopy(ui), copy.deepcopy(data)
    return None


def defaults_for_kind(kind: str, *, template_id: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    tid = (template_id or "").strip().lower()
    if tid:
        path = template_path_for_template_id(tid)
        if path:
            t = _load_kind_template(path)
            if t:
                return t
    k = (kind or "custom").strip().lower()
    if k == "custom":
        return copy.deepcopy(_CUSTOM_UI), copy.deepcopy(_CUSTOM_DATA)
    path = template_path_for_kind(k)
    if path:
        t = _load_kind_template(path)
        if t:
            return t
    return copy.deepcopy(_CUSTOM_UI), copy.deepcopy(_CUSTOM_DATA)
