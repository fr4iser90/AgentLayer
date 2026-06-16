"""Load knob metadata from docs/benchmarks/knob-registry.yaml."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_REGISTRY_PATH = _REPO_ROOT / "docs" / "benchmarks" / "knob-registry.yaml"


@lru_cache(maxsize=1)
def load_knob_registry(*, path: str | None = None) -> dict[str, Any]:
    reg_path = Path(path) if path else _DEFAULT_REGISTRY_PATH
    if not reg_path.is_file():
        logger.warning("knob registry missing: %s", reg_path)
        return {"version": 0, "ui_groups": [], "knobs": []}
    raw = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {"version": 0, "ui_groups": [], "knobs": []}
    return raw


def knob_by_id(knob_id: str) -> dict[str, Any] | None:
    kid = (knob_id or "").strip()
    if not kid:
        return None
    for k in load_knob_registry().get("knobs") or []:
        if isinstance(k, dict) and str(k.get("id") or "") == kid:
            return dict(k)
    return None


def all_knobs() -> list[dict[str, Any]]:
    rows = load_knob_registry().get("knobs") or []
    return [dict(r) for r in rows if isinstance(r, dict) and r.get("id")]


HARNESS_KNOB_LAYERS = frozenset({"runtime_config", "agent_yaml", "router_yaml", "operator"})


def is_harness_knob(knob: dict[str, Any]) -> bool:
    return str(knob.get("layer") or "") in HARNESS_KNOB_LAYERS
