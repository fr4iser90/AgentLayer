"""Settings for external agent runtimes (Qwen Code and friends).

Star-imported by ``config.py`` so values are reachable as ``config.AGENT_EXTERNAL_*``.
Everything is off unless the operator opts in: an uninstalled vendor binary must not
change anything else in the product.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from apps.backend.infrastructure.platform.config_env import env_bool as _env_bool
from apps.backend.infrastructure.platform.config_env import env_int as _env_int

logger = logging.getLogger(__name__)

# Master switch for running agent turns in an external runtime process at all.
EXTERNAL_RUNTIME_ENABLED = _env_bool("AGENT_EXTERNAL_RUNTIME_ENABLED", False)
# Ceiling for permission modes. ``yolo`` (unrestricted shell) needs this explicitly.
EXTERNAL_RUNTIME_ALLOW_YOLO = _env_bool("AGENT_EXTERNAL_RUNTIME_ALLOW_YOLO", False)
EXTERNAL_RUNTIME_TIMEOUT_SEC = max(60, min(_env_int("AGENT_EXTERNAL_RUNTIME_TIMEOUT_SEC", 1800), 7200))
EXTERNAL_RUNTIME_MAX_TURNS = max(1, min(_env_int("AGENT_EXTERNAL_RUNTIME_MAX_TURNS", 60), 500))
# Writable HOME for vendor child processes: they persist sessions under ``~/.<vendor>``.
# After ``gosu`` drops to a numeric uid, ``$HOME`` is not reliably writable — set it here.
EXTERNAL_RUNTIME_HOME = (os.environ.get("AGENT_EXTERNAL_RUNTIME_HOME") or "/data/external_runtimes").strip()
# When the declared runtime is unavailable, fall back to AgentLayer's own planner loop
# instead of failing the turn. Off by default: a silent downgrade changes who is coding.
EXTERNAL_RUNTIME_FALLBACK_INTERNAL = _env_bool("AGENT_EXTERNAL_RUNTIME_FALLBACK_INTERNAL", False)

# --- Qwen Code adapter ---
QWEN_RUNTIME_ENABLED = _env_bool("AGENT_QWEN_ENABLED", True)
# Binary name or absolute path; the SDK spawns it per session.
QWEN_BIN = (os.environ.get("AGENT_QWEN_BIN") or "qwen").strip() or "qwen"
# Empty = use the model AgentLayer resolved for this turn (provider pass-through).
QWEN_MODEL = (os.environ.get("AGENT_QWEN_MODEL") or "").strip() or None
_QWEN_MODE_RAW = (os.environ.get("AGENT_QWEN_PERMISSION_MODE") or "auto-edit").strip().lower()
QWEN_PERMISSION_MODE = _QWEN_MODE_RAW if _QWEN_MODE_RAW in ("plan", "auto-edit", "yolo") else "auto-edit"
if _QWEN_MODE_RAW and _QWEN_MODE_RAW not in ("plan", "auto-edit", "yolo"):
    logger.warning("unknown AGENT_QWEN_PERMISSION_MODE %r — using auto-edit", _QWEN_MODE_RAW)
# Comma-separated vendor tool names to deny the external agent (e.g. "webFetch,agent").
QWEN_EXCLUDE_TOOLS: tuple[str, ...] = tuple(
    part.strip() for part in (os.environ.get("AGENT_QWEN_EXCLUDE_TOOLS") or "").split(",") if part.strip()
)


def external_runtime_home_dir() -> Path:
    """Absolute, operator-owned base dir for vendor runtime state (sessions, settings)."""
    return Path(EXTERNAL_RUNTIME_HOME).expanduser()


__all__ = [
    "EXTERNAL_RUNTIME_ENABLED",
    "EXTERNAL_RUNTIME_ALLOW_YOLO",
    "EXTERNAL_RUNTIME_TIMEOUT_SEC",
    "EXTERNAL_RUNTIME_MAX_TURNS",
    "EXTERNAL_RUNTIME_HOME",
    "EXTERNAL_RUNTIME_FALLBACK_INTERNAL",
    "QWEN_RUNTIME_ENABLED",
    "QWEN_BIN",
    "QWEN_MODEL",
    "QWEN_PERMISSION_MODE",
    "QWEN_EXCLUDE_TOOLS",
    "external_runtime_home_dir",
]
