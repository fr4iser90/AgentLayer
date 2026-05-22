"""Safe get/set for dashboard ``data`` JSON (mirrors frontend ``dashboardDataPaths``)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _unsafe_segment(seg: str) -> bool:
    return seg in ("__proto__", "constructor", "prototype")


def get_path(obj: dict[str, Any], path: str) -> Any:
    if not path or not path.strip():
        return None
    p = path.strip()
    if "." not in p:
        if _unsafe_segment(p):
            return None
        return obj.get(p)
    segs = [s for s in p.split(".") if s]
    cur: Any = obj
    for seg in segs:
        if _unsafe_segment(seg):
            return None
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                i = int(seg)
            except ValueError:
                return None
            if i < 0 or i >= len(cur):
                return None
            cur = cur[i]
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def set_path(obj: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    """Return a new dict with ``path`` set to ``value`` (immutable-style)."""
    if not path or not path.strip():
        return dict(obj)
    p = path.strip()
    if "." not in p:
        if _unsafe_segment(p):
            return dict(obj)
        out = dict(obj)
        out[p] = value
        return out
    segs = [s for s in p.split(".") if s]
    if any(_unsafe_segment(s) for s in segs):
        return dict(obj)
    head, *tail = segs
    tail_path = ".".join(tail)
    raw = obj.get(head)

    if isinstance(raw, list):
        try:
            idx = int(tail[0])
        except (ValueError, IndexError):
            out = dict(obj)
            out[head] = value
            return out
        arr = list(raw)
        if len(tail) == 1:
            while len(arr) <= idx:
                arr.append(None)
            arr[idx] = value
            out = dict(obj)
            out[head] = arr
            return out
        elem = arr[idx] if 0 <= idx < len(arr) else None
        inner: dict[str, Any] = (
            dict(elem) if isinstance(elem, dict) else {}
        )
        arr = list(raw)
        while len(arr) <= idx:
            arr.append({})
        arr[idx] = set_path(inner, ".".join(tail[1:]), value)
        out = dict(obj)
        out[head] = arr
        return out

    child: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    out = dict(obj)
    out[head] = set_path(child, tail_path, value)
    return out


def top_level_key(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    return p.split(".", 1)[0].strip()


def apply_data_patches(
    data: dict[str, Any],
    patches: list[dict[str, Any]],
    *,
    allowed_top_keys: set[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """
    Apply ``{path, value}`` patches. If ``allowed_top_keys`` is set, reject paths
    whose top-level key is not allowed (granular block shares).
    """
    out = deepcopy(data)
    for i, patch in enumerate(patches):
        if not isinstance(patch, dict):
            return out, f"patches[{i}] must be an object"
        path = str(patch.get("path") or "").strip()
        if not path:
            return out, f"patches[{i}].path is required"
        if path.startswith("_") and path != "_agentlayer":
            return out, f"patches[{i}]: reserved path {path!r}"
        if allowed_top_keys is not None:
            tk = top_level_key(path)
            if tk and tk not in allowed_top_keys:
                return out, f"patches[{i}]: path {path!r} not in allowed data keys"
        if "value" not in patch:
            return out, f"patches[{i}].value is required"
        out = set_path(out, path, patch["value"])
    return out, None
