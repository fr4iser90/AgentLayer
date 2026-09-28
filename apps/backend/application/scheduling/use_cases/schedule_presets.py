"""The schedule preset templates shipped under ``plugins/schedules/presets``.

Reading that directory used to be written twice — once in the user endpoint that feeds
the template picker, once in the operator tool — each with its own idea of when a
template counts. A preset the picker offered could therefore be missing from the
operator's list, or the other way round. One read, one shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def schedule_presets_dir() -> Path:
    from apps.backend.infrastructure.platform.config import PLUGINS_DIR

    return PLUGINS_DIR / "schedules" / "presets"


def read_schedule_presets() -> list[dict[str, Any]]:
    """Every usable template, ordered by file name.

    A file that is not valid JSON, is not an object, or is missing ``id`` or ``label``
    is skipped rather than raising: one broken template must not empty the picker for
    everyone. ``job`` is the payload to copy into a new schedule, empty when absent.
    """
    root = schedule_presets_dir()
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        pid = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not pid or not label:
            continue
        job = raw.get("job")
        rows.append(
            {
                "id": pid,
                "label": label,
                "description": str(raw.get("description") or "").strip(),
                "job": job if isinstance(job, dict) else {},
            }
        )
    return rows