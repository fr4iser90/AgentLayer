"""Lightweight response field extraction (dot paths, no external deps)."""

from __future__ import annotations

import re
from typing import Any


_TEMPLATE_RE = re.compile(r"\{\{(\w+)\}\}")


def extract_path(data: Any, path: str | None) -> Any:
    if not path or not str(path).strip():
        return data
    cur = data
    for part in str(path).strip().split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError, TypeError):
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def apply_template(value: Any, params: dict[str, Any]) -> Any:
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in params:
                return m.group(0)
            return str(params[key])

        return _TEMPLATE_RE.sub(repl, value)
    if isinstance(value, dict):
        return {k: apply_template(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [apply_template(v, params) for v in value]
    return value
