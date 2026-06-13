"""Descriptive statistics over numeric lists."""

from __future__ import annotations

import json
import statistics
from typing import Any, Callable

__version__ = "1.0.0"
TOOL_ID = "math_statistics"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "math"
TOOL_LABEL = "Math statistics"
TOOL_DESCRIPTION = (
    "Descriptive stats on a numeric list: count, sum, min, max, mean, median, "
    "variance, std, range, and optional percentile."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("math.statistics",)

_OPS = frozenset(
    {
        "summary",
        "count",
        "sum",
        "min",
        "max",
        "mean",
        "median",
        "var",
        "std",
        "range",
        "percentile",
    }
)


def _parse_values(raw: Any) -> list[float]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("values must be a non-empty array of numbers")
    out: list[float] = []
    for i, v in enumerate(raw):
        try:
            out.append(float(v))
        except (TypeError, ValueError) as e:
            raise ValueError(f"values[{i}] is not numeric") from e
    return out


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        raise ValueError("empty values")
    if p <= 0:
        return sorted_vals[0]
    if p >= 100:
        return sorted_vals[-1]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def _summary(values: list[float]) -> dict[str, float]:
    s = sorted(values)
    return {
        "count": float(len(values)),
        "sum": float(sum(values)),
        "min": float(s[0]),
        "max": float(s[-1]),
        "mean": float(statistics.fmean(values)),
        "median": float(statistics.median(values)),
        "var": float(statistics.pvariance(values)) if len(values) > 1 else 0.0,
        "std": float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
        "range": float(s[-1] - s[0]),
    }


def math_statistics(arguments: dict[str, Any]) -> str:
    op = str(arguments.get("operation") or "summary").strip().lower()
    if op not in _OPS:
        return json.dumps(
            {"ok": False, "error": f"operation must be one of: {', '.join(sorted(_OPS))}"}
        )
    try:
        values = _parse_values(arguments.get("values"))
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)})

    if op == "summary":
        payload: dict[str, Any] = {"ok": True, "operation": op, "values": values, "stats": _summary(values)}
        return json.dumps(payload)

    if op == "percentile":
        try:
            p = float(arguments.get("percentile", 50))
        except (TypeError, ValueError):
            return json.dumps({"ok": False, "error": "percentile must be a number 0–100"})
        if p < 0 or p > 100:
            return json.dumps({"ok": False, "error": "percentile must be between 0 and 100"})
        result = _percentile(sorted(values), p)
        return json.dumps(
            {
                "ok": True,
                "operation": op,
                "percentile": p,
                "result": result,
                "values": values,
            }
        )

    s = _summary(values)
    key_map = {
        "count": "count",
        "sum": "sum",
        "min": "min",
        "max": "max",
        "mean": "mean",
        "median": "median",
        "var": "var",
        "std": "std",
        "range": "range",
    }
    return json.dumps(
        {
            "ok": True,
            "operation": op,
            "result": s[key_map[op]],
            "values": values,
        }
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "math_statistics": math_statistics,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "math_statistics",
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "required": ["values"],
                "properties": {
                    "values": {
                        "type": "array",
                        "items": {"type": "number"},
                        "TOOL_DESCRIPTION": "Non-empty list of numbers",
                    },
                    "operation": {
                        "type": "string",
                        "enum": sorted(_OPS),
                        "TOOL_DESCRIPTION": "Default summary returns all common stats",
                    },
                    "percentile": {
                        "type": "number",
                        "TOOL_DESCRIPTION": "Required when operation=percentile (0–100)",
                    },
                },
            },
        },
    },
]
