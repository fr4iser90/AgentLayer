"""Structured percentage calculations (no expression parsing)."""

from __future__ import annotations

import json
from typing import Any, Callable

__version__ = "1.0.0"
TOOL_ID = "math_percentage"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "math"
TOOL_LABEL = "Math percentage"
TOOL_DESCRIPTION = (
    "Percentage math: X% of Y, increase/decrease by X%, what % is A of B, percent change between two values."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("math.percentage",)

_MODES = frozenset({"of", "increase", "decrease", "part_of_whole", "change"})


def _num(raw: Any, field: str) -> float:
    if raw is None or raw == "":
        raise ValueError(f"{field} is required")
    return float(raw)


def math_percentage(arguments: dict[str, Any]) -> str:
    mode = str(arguments.get("mode") or "of").strip().lower()
    if mode not in _MODES:
        return json.dumps(
            {
                "ok": False,
                "error": f"mode must be one of: {', '.join(sorted(_MODES))}",
            }
        )
    try:
        if mode == "of":
            value = _num(arguments.get("value"), "value")
            rate = _num(arguments.get("rate"), "rate")
            result = value * rate / 100.0
            detail = {"value": value, "rate": rate, "mode": mode}
        elif mode in ("increase", "decrease"):
            value = _num(arguments.get("value"), "value")
            rate = _num(arguments.get("rate"), "rate")
            factor = 1.0 + rate / 100.0 if mode == "increase" else 1.0 - rate / 100.0
            result = value * factor
            detail = {"value": value, "rate": rate, "mode": mode, "factor": factor}
        elif mode == "part_of_whole":
            part = _num(arguments.get("part"), "part")
            whole = _num(arguments.get("whole"), "whole")
            if whole == 0:
                return json.dumps({"ok": False, "error": "whole must not be zero"})
            result = (part / whole) * 100.0
            detail = {"part": part, "whole": whole, "mode": mode}
        else:  # change
            old_value = _num(arguments.get("old_value"), "old_value")
            new_value = _num(arguments.get("new_value"), "new_value")
            if old_value == 0:
                return json.dumps({"ok": False, "error": "old_value must not be zero"})
            result = ((new_value - old_value) / old_value) * 100.0
            detail = {"old_value": old_value, "new_value": new_value, "mode": mode}
    except (TypeError, ValueError) as e:
        return json.dumps({"ok": False, "error": str(e)})

    return json.dumps({"ok": True, "result": result, **detail})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "math_percentage": math_percentage,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "math_percentage",
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "required": ["mode"],
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": sorted(_MODES),
                        "TOOL_DESCRIPTION": (
                            "of = rate% of value; increase/decrease = apply rate% to value; "
                            "part_of_whole = what % is part of whole; change = % change old→new"
                        ),
                    },
                    "value": {"type": "number", "TOOL_DESCRIPTION": "Base value (of/increase/decrease)"},
                    "rate": {"type": "number", "TOOL_DESCRIPTION": "Percentage rate for of/increase/decrease"},
                    "part": {"type": "number", "TOOL_DESCRIPTION": "Part value for part_of_whole"},
                    "whole": {"type": "number", "TOOL_DESCRIPTION": "Whole value for part_of_whole"},
                    "old_value": {"type": "number", "TOOL_DESCRIPTION": "Starting value for change"},
                    "new_value": {"type": "number", "TOOL_DESCRIPTION": "Ending value for change"},
                },
            },
        },
    },
]
