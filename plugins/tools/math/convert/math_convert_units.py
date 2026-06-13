"""Unit conversion (length, weight, temperature, data)."""

from __future__ import annotations

import json
from typing import Any, Callable

__version__ = "1.0.0"
TOOL_ID = "math_convert_units"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "math"
TOOL_LABEL = "Math unit convert"
TOOL_DESCRIPTION = (
    "Convert numeric values between common units: length (m, km, cm, mm, mile, yard, foot, inch), "
    "weight (kg, g, lb, oz), temperature (c, f, k), data (b, kb, mb, gb, tb)."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("math.convert",)

# Canonical base: meters, kilograms, bytes, celsius
_LENGTH_TO_M: dict[str, float] = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "km": 1000.0,
    "kilometer": 1000.0,
    "kilometers": 1000.0,
    "cm": 0.01,
    "centimeter": 0.01,
    "centimeters": 0.01,
    "mm": 0.001,
    "millimeter": 0.001,
    "millimeters": 0.001,
    "mile": 1609.344,
    "miles": 1609.344,
    "yard": 0.9144,
    "yards": 0.9144,
    "foot": 0.3048,
    "feet": 0.3048,
    "ft": 0.3048,
    "inch": 0.0254,
    "inches": 0.0254,
    "in": 0.0254,
}

_WEIGHT_TO_KG: dict[str, float] = {
    "kg": 1.0,
    "kilogram": 1.0,
    "kilograms": 1.0,
    "g": 0.001,
    "gram": 0.001,
    "grams": 0.001,
    "lb": 0.45359237,
    "lbs": 0.45359237,
    "pound": 0.45359237,
    "pounds": 0.45359237,
    "oz": 0.028349523125,
    "ounce": 0.028349523125,
    "ounces": 0.028349523125,
}

_DATA_TO_B: dict[str, float] = {
    "b": 1.0,
    "byte": 1.0,
    "bytes": 1.0,
    "kb": 1024.0,
    "mb": 1024.0**2,
    "gb": 1024.0**3,
    "tb": 1024.0**4,
}

_TEMP_UNITS = frozenset({"c", "celsius", "f", "fahrenheit", "k", "kelvin"})


def _norm_unit(raw: Any) -> str:
    return str(raw or "").strip().lower().replace("°", "")


def _category_for(from_u: str, to_u: str) -> str | None:
    if from_u in _LENGTH_TO_M and to_u in _LENGTH_TO_M:
        return "length"
    if from_u in _WEIGHT_TO_KG and to_u in _WEIGHT_TO_KG:
        return "weight"
    if from_u in _DATA_TO_B and to_u in _DATA_TO_B:
        return "data"
    if from_u in _TEMP_UNITS and to_u in _TEMP_UNITS:
        return "temperature"
    return None


def _convert_temperature(value: float, from_u: str, to_u: str) -> float:
    fu = "c" if from_u in ("c", "celsius") else "f" if from_u in ("f", "fahrenheit") else "k"
    tu = "c" if to_u in ("c", "celsius") else "f" if to_u in ("f", "fahrenheit") else "k"
    if fu == "c":
        c = value
    elif fu == "f":
        c = (value - 32.0) * 5.0 / 9.0
    else:
        c = value - 273.15
    if tu == "c":
        return c
    if tu == "f":
        return c * 9.0 / 5.0 + 32.0
    return c + 273.15


def math_convert_units(arguments: dict[str, Any]) -> str:
    try:
        value = float(arguments.get("value"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "value is required and must be numeric"})
    from_u = _norm_unit(arguments.get("from_unit"))
    to_u = _norm_unit(arguments.get("to_unit"))
    if not from_u or not to_u:
        return json.dumps({"ok": False, "error": "from_unit and to_unit are required"})

    category = _category_for(from_u, to_u)
    if category is None:
        return json.dumps(
            {
                "ok": False,
                "error": "incompatible or unknown units — use matching length, weight, temperature, or data units",
                "from_unit": from_u,
                "to_unit": to_u,
            }
        )

    if category == "temperature":
        result = _convert_temperature(value, from_u, to_u)
    elif category == "length":
        result = (value * _LENGTH_TO_M[from_u]) / _LENGTH_TO_M[to_u]
    elif category == "weight":
        result = (value * _WEIGHT_TO_KG[from_u]) / _WEIGHT_TO_KG[to_u]
    else:
        result = (value * _DATA_TO_B[from_u]) / _DATA_TO_B[to_u]

    return json.dumps(
        {
            "ok": True,
            "value": value,
            "from_unit": from_u,
            "to_unit": to_u,
            "category": category,
            "result": result,
        }
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "math_convert_units": math_convert_units,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "math_convert_units",
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "required": ["value", "from_unit", "to_unit"],
                "properties": {
                    "value": {"type": "number", "TOOL_DESCRIPTION": "Numeric amount to convert"},
                    "from_unit": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Source unit (e.g. km, lb, c, mb)",
                    },
                    "to_unit": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Target unit (e.g. miles, kg, f, gb)",
                    },
                },
            },
        },
    },
]
