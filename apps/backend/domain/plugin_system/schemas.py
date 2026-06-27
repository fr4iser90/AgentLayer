"""Plugin manifest validation."""
from __future__ import annotations

from collections.abc import Mapping


def validate_plugin_manifest(raw: Mapping[str, object]) -> dict[str, object]:
    manifest = dict(raw)
    plugin_id = str(manifest.get("id") or "").strip()
    label = str(manifest.get("label") or "").strip()
    if not plugin_id:
        raise ValueError("plugin manifest id must not be blank")
    if not label:
        raise ValueError("plugin manifest label must not be blank")
    manifest["id"] = plugin_id
    manifest["label"] = label
    return manifest
