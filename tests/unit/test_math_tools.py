"""Math specialist tools."""

from __future__ import annotations

import json

from plugins.tools.math.convert.math_convert_units import math_convert_units
from plugins.tools.math.eval.math_eval import math_eval
from plugins.tools.math.percentage.math_percentage import math_percentage
from plugins.tools.math.stats.math_statistics import math_statistics


def test_math_eval_basic() -> None:
    out = json.loads(math_eval({"expression": "(2+3)*4"}))
    assert out["ok"] is True
    assert out["result"] == 20.0


def test_math_eval_rejects_code() -> None:
    out = json.loads(math_eval({"expression": "__import__('os').system('id')"}))
    assert out["ok"] is False


def test_math_percentage_of() -> None:
    out = json.loads(math_percentage({"mode": "of", "value": 200, "rate": 15}))
    assert out["ok"] is True
    assert out["result"] == 30.0


def test_math_percentage_increase() -> None:
    out = json.loads(math_percentage({"mode": "increase", "value": 100, "rate": 19}))
    assert out["ok"] is True
    assert out["result"] == 119.0


def test_math_percentage_part_of_whole() -> None:
    out = json.loads(math_percentage({"mode": "part_of_whole", "part": 25, "whole": 200}))
    assert out["ok"] is True
    assert out["result"] == 12.5


def test_math_convert_km_miles() -> None:
    out = json.loads(math_convert_units({"value": 10, "from_unit": "km", "to_unit": "miles"}))
    assert out["ok"] is True
    assert out["result"] > 6.2 and out["result"] < 6.3


def test_math_convert_celsius_fahrenheit() -> None:
    out = json.loads(math_convert_units({"value": 0, "from_unit": "c", "to_unit": "f"}))
    assert out["ok"] is True
    assert out["result"] == 32.0


def test_math_statistics_summary() -> None:
    out = json.loads(math_statistics({"values": [2, 4, 6, 8]}))
    assert out["ok"] is True
    assert out["stats"]["mean"] == 5.0
    assert out["stats"]["median"] == 5.0
    assert out["stats"]["count"] == 4.0


def test_math_statistics_percentile() -> None:
    out = json.loads(
        math_statistics({"values": [1, 2, 3, 4, 5], "operation": "percentile", "percentile": 50})
    )
    assert out["ok"] is True
    assert out["result"] == 3.0
