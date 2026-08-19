"""Golden checks for formula expressions used by private dashboard formula_calc blocks."""

from __future__ import annotations

import ast
import operator as op


_BINOPS = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
}
_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}


def _eval(node: ast.AST, values: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise KeyError(node.id)
        return float(values[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return float(_BINOPS[type(node.op)](_eval(node.left, values), _eval(node.right, values)))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return float(_UNARY[type(node.op)](_eval(node.operand, values)))
    raise ValueError(f"unsupported: {type(node).__name__}")


def eval_expr(expr: str, values: dict[str, float]) -> float:
    tree = ast.parse(expr, mode="eval")
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            raise ValueError("calls not allowed")
    return _eval(tree, values)


def test_anion_gap_expr() -> None:
    assert eval_expr("na-(cl+hco3)", {"na": 140, "cl": 104, "hco3": 24}) == 12.0


def test_aa_gradient_expr() -> None:
    v = {"fio2": 0.21, "patm": 760, "ph2o": 47, "paco2": 40, "r": 0.8, "pao2": 95}
    pao2 = eval_expr("fio2*(patm-ph2o)-(paco2/r)", v)
    aa = eval_expr("(fio2*(patm-ph2o)-(paco2/r))-pao2", v)
    assert abs(pao2 - 99.73) < 0.05
    assert abs(aa - 4.73) < 0.05


def test_ibw_and_map() -> None:
    ibw = eval_expr("sex_base+2.3*((height_cm/2.54)-60)", {"sex_base": 50, "height_cm": 180})
    assert abs(ibw - 74.99) < 0.2
    assert abs(eval_expr("dbp+(sbp-dbp)/3", {"sbp": 120, "dbp": 80}) - (80 + 40 / 3)) < 1e-9


def test_private_dashboard_bundles_discoverable() -> None:
    from apps.backend.infrastructure.dashboards.dashboard_bundle import bundles_by_kind

    kinds = bundles_by_kind()
    for k in ("knowledge", "hygiene", "crisis", "bga", "icu", "meds", "abx"):
        assert k in kinds, f"missing private kind {k} (is plugins/dashboards/_private present?)"
