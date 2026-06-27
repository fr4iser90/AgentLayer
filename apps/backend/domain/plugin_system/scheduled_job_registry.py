"""
Registry for **scheduled (cron) jobs** — not agent tools, not ComfyUI graphs.

Scans the same tool directories as the tool registry, but only loads modules that define
``HANDLERS`` + ``RUN_EVERY_MINUTES``. Those run on an interval in ``apps/backend/infrastructure/cron.py``.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from apps.backend.domain.plugin_system.registry import (
    _iter_tool_py_files,
    _stable_module_slug,
    tool_scan_directories,
)

logger = logging.getLogger(__name__)

ScheduledJobHandler = Callable[[dict[str, Any]], str]


class ScheduledJobRegistry:
    """Collects periodic background jobs from Python modules (HANDLERS + RUN_EVERY_MINUTES)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: list[dict[str, Any]] = []

    def load_all(self) -> None:
        with self._lock:
            self._jobs.clear()

            dirs = tool_scan_directories()
            if not dirs:
                return

            for dir_idx, directory in enumerate(dirs):
                if not directory.is_dir():
                    continue
                for path in _iter_tool_py_files(directory):
                    try:
                        slug = _stable_module_slug(directory, path, dir_idx)
                        mod_name = f"agent_scheduled_job_{slug}"
                        spec = importlib.util.spec_from_file_location(mod_name, path)
                        if spec is None or spec.loader is None:
                            continue
                        mod = importlib.util.module_from_spec(spec)
                        sys.modules[mod_name] = mod
                        spec.loader.exec_module(mod)
                    except Exception:
                        continue

                    handlers = getattr(mod, "HANDLERS", None)
                    minutes = getattr(mod, "RUN_EVERY_MINUTES", None)

                    if not isinstance(handlers, dict) or not handlers:
                        continue
                    if not isinstance(minutes, (int, float)) or minutes <= 0:
                        continue

                    run_on_start = getattr(mod, "RUN_ON_STARTUP", False)
                    handler_name = next(iter(handlers.keys()))

                    self._jobs.append(
                        {
                            "name": handler_name,
                            "handler": handlers[handler_name],
                            "interval_seconds": minutes * 60,
                            "last_run": 0.0,
                            "run_on_start": run_on_start,
                        }
                    )

                    logger.info(
                        "Registered scheduled job: %s every %s minutes (cron, not LLM tools)",
                        handler_name,
                        minutes,
                    )

    @property
    def jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._jobs)


_scheduled_job_registry: ScheduledJobRegistry | None = None
_scheduled_job_registry_lock = threading.Lock()


def get_scheduled_job_registry() -> ScheduledJobRegistry:
    global _scheduled_job_registry
    with _scheduled_job_registry_lock:
        if _scheduled_job_registry is None:
            _scheduled_job_registry = ScheduledJobRegistry()
            _scheduled_job_registry.load_all()
        return _scheduled_job_registry
