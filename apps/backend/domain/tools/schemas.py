"""Tool schema validation."""
from __future__ import annotations

from collections.abc import Mapping


def validate_tool_input_schema(schema: Mapping[str, object] | None) -> dict[str, object]:
    if schema is None:
        return {}
    result = dict(schema)
    if result.get("type") not in (None, "object"):
        raise ValueError("tool input schema root must be an object")
    return result


def validate_tool_arguments(arguments: Mapping[str, object] | None) -> dict[str, object]:
    return dict(arguments or {})
