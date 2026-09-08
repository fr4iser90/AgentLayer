"""Frontend layout-mode helpers mirrored for backend contract checks.

The real helpers live in apps/frontend/.../layoutMode.ts; this test guards the
JSON shape the API must preserve (mode + canvas viewport).
"""

from __future__ import annotations


def _normalize_ui_layout_mode(ul: dict) -> dict:
    mode = str(ul.get("mode") or "grid").strip().lower()
    if mode != "canvas":
        mode = "grid"
    out = {**ul, "mode": mode}
    if mode == "grid":
        out.pop("canvas", None)
    elif isinstance(ul.get("canvas"), dict):
        out["canvas"] = ul["canvas"]
    return out


def test_default_mode_is_grid() -> None:
    out = _normalize_ui_layout_mode({"version": 1, "blocks": []})
    assert out["mode"] == "grid"
    assert "canvas" not in out


def test_canvas_mode_preserved() -> None:
    out = _normalize_ui_layout_mode(
        {
            "version": 2,
            "mode": "canvas",
            "canvas": {"zoom": 1.2, "panX": 10, "panY": -4},
            "blocks": [{"id": "a", "type": "markdown", "grid": {"x": 0, "y": 0, "w": 4, "h": 3}, "props": {}}],
        }
    )
    assert out["mode"] == "canvas"
    assert out["canvas"]["zoom"] == 1.2


def test_unknown_mode_falls_back_to_grid() -> None:
    out = _normalize_ui_layout_mode({"version": 1, "mode": "whiteboard", "blocks": []})
    assert out["mode"] == "grid"
