"""Load co-located ``*.router.yaml`` phrase packs next to plugin tool modules."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def co_located_router_yaml_path(module_source: str) -> Path | None:
    """``file:/path/to/tool.py`` → ``/path/to/tool.router.yaml`` when present."""
    raw = (module_source or "").strip()
    if not raw.startswith("file:"):
        return None
    py_path = Path(raw[5:])
    candidate = py_path.with_name(f"{py_path.stem}.router.yaml")
    return candidate if candidate.is_file() else None


def _normalize_phrase(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip().lower()
    return s or None


def _collect_phrases(node: Any) -> list[str]:
    """Flatten ``phrases`` tree (locale keys are authoring-only; all merge for routing)."""
    out: list[str] = []
    if isinstance(node, str):
        p = _normalize_phrase(node)
        if p:
            out.append(p)
    elif isinstance(node, list):
        for item in node:
            out.extend(_collect_phrases(item))
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_collect_phrases(value))
    return out


def load_co_located_router_phrases(module_source: str) -> tuple[str | None, tuple[str, ...]]:
    """
    Parse co-located router YAML for a plugin module.

    Returns ``(domain_override, phrases)``. Locale keys under ``phrases`` are ignored at
    match time — all languages are unioned (user locale is not used for routing).
    """
    path = co_located_router_yaml_path(module_source)
    if path is None:
        return None, ()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to read router phrases %s", path, exc_info=True)
        return None, ()

    if not isinstance(raw, dict):
        logger.warning("router phrases %s: root must be a mapping", path)
        return None, ()

    domain_raw = raw.get("domain")
    domain: str | None = None
    if isinstance(domain_raw, str) and domain_raw.strip():
        domain = domain_raw.strip().lower()

    phrases_node = raw.get("phrases")
    if phrases_node is None:
        return domain, ()

    seen: set[str] = set()
    ordered: list[str] = []
    for p in _collect_phrases(phrases_node):
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return domain, tuple(ordered)
