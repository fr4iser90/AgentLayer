"""Collection schema validation."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_collection_title(title: str) -> str:
    value = title.strip()
    if len(value) > 200:
        raise ValueError("collection title is too long")
    return value


def validate_collection_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if len(metadata) > 100:
        raise ValueError("collection metadata may contain at most 100 keys")
    return {str(key): value for key, value in metadata.items() if str(key).strip()}


def validate_collection_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(row)
    if "id" in result and not str(result["id"]).strip():
        raise ValueError("collection row id must not be blank")
    return result
