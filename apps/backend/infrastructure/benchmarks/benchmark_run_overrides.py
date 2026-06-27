"""In-process benchmark run overrides for harness knobs.

Benchmarks may specify run-level harness overrides (do not persist into agent_config_overrides).
During execution we bind ``benchmark_run_id`` in identity context; `agent_config_effective`
can then read per-run overrides from this module.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

_LOCK = threading.Lock()
_RUN_OVERRIDES: dict[uuid.UUID, dict[str, Any]] = {}


def set_run_overrides(run_id: uuid.UUID, overrides: dict[str, Any]) -> None:
    with _LOCK:
        _RUN_OVERRIDES[run_id] = dict(overrides or {})


def get_run_override(run_id: uuid.UUID, knob_id: str) -> Any | None:
    with _LOCK:
        data = _RUN_OVERRIDES.get(run_id)
        if not data:
            return None
        return data.get(knob_id)


def clear_run_overrides(run_id: uuid.UUID) -> None:
    with _LOCK:
        _RUN_OVERRIDES.pop(run_id, None)

