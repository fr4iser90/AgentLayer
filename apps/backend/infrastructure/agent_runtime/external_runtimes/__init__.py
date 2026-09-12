"""External agent runtime adapters (import this package to register them).

Adding a runtime = one adapter module in this package plus one line in ``_ADAPTERS``.
Each adapter self-registers with ``domain/agent_runtime/external_runtime.py`` on import;
``server_lifecycle`` imports this package so registration happens at startup.

Adapters must stay import-safe without their vendor installed: probe in ``available()``,
import the SDK lazily inside ``run()``.
"""

from __future__ import annotations

from apps.backend.infrastructure.agent_runtime.external_runtimes import (  # noqa: F401
    qwen_code,
)

_ADAPTERS = (qwen_code,)

__all__ = ["qwen_code"]
