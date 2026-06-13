"""Safe numeric expression evaluation (no arbitrary code execution)."""

from __future__ import annotations

import ast
import json
import math
import operator
from typing import Any, Callable

__version__ = "1.0.0"
TOOL_ID = "math_eval"
TOOL_BUCKET = "meta"
TOOL_DOMAIN = "math"
TOOL_LABEL = "Math evaluate"
TOOL_DESCRIPTION = (
    "Evaluate a numeric expression with + - * / // % **, parentheses, and common math functions "
    "(sqrt, sin, cos, tan, log, exp, abs, round, min, max, pi, e)."
)
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("math.evaluate",)

_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_FUNCS: dict[str, Callable[..., float]] = {
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
}
_CONSTS = {"pi": math.pi, "e": math.e}


class _UnsafeExpression(ValueError):
    pass


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or node.value is None:
            raise _UnsafeExpression("unsupported constant")
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise _UnsafeExpression("unsupported constant type")
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return float(_UNARY[type(node.op)](_eval_node(node.operand)))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return float(_BINOPS[type(node.op)](_eval_node(node.left), _eval_node(node.right)))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise _UnsafeExpression("only simple function calls allowed")
        fn_name = node.func.id
        if fn_name not in _FUNCS:
            raise _UnsafeExpression(f"function not allowed: {fn_name}")
        if node.keywords:
            raise _UnsafeExpression("keyword arguments not allowed")
        args = [_eval_node(a) for a in node.args]
        return float(_FUNCS[fn_name](*args))
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return float(_CONSTS[node.id])
        raise _UnsafeExpression(f"unknown name: {node.id}")
    raise _UnsafeExpression(f"unsupported syntax: {type(node).__name__}")


def _safe_eval(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def math_eval(arguments: dict[str, Any]) -> str:
    expr = str(arguments.get("expression") or "").strip()
    if not expr:
        return json.dumps({"ok": False, "error": "expression is required"})
    try:
        value = _safe_eval(expr)
    except SyntaxError as e:
        return json.dumps({"ok": False, "error": f"invalid syntax: {e.msg}"})
    except (ZeroDivisionError, OverflowError, ValueError, _UnsafeExpression) as e:
        return json.dumps({"ok": False, "error": str(e)})
    return json.dumps({"ok": True, "expression": expr, "result": value})


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "math_eval": math_eval,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "math_eval",
            "TOOL_DESCRIPTION": TOOL_DESCRIPTION,
            "parameters": {
                "type": "object",
                "required": ["expression"],
                "properties": {
                    "expression": {
                        "type": "string",
                        "TOOL_DESCRIPTION": (
                            "Numeric expression, e.g. (2+3)*4, sqrt(16), sin(pi/2), log(e)"
                        ),
                    },
                },
            },
        },
    },
]
