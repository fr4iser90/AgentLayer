"""
Chat completion facade — implementation split across ``agent_*`` modules.

See ``docs/adr/0001-tool-and-agent-architecture.md``.
"""
from __future__ import annotations

from apps.backend.domain import agent_io as _agent_io
from apps.backend.domain import agent_planner as _agent_planner
from apps.backend.domain import agent_prompts as _agent_prompts
from apps.backend.domain import agent_tools as _agent_tools
from apps.backend.domain.agent_planner import chat_completion

_EXPORT_MODULES = (_agent_tools, _agent_prompts, _agent_io, _agent_planner)


def __getattr__(name: str):  # noqa: ANN001
    for mod in _EXPORT_MODULES:
        if hasattr(mod, name):
            return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    names = {"chat_completion"}
    for mod in _EXPORT_MODULES:
        names.update(n for n in dir(mod) if not n.startswith("__"))
    return sorted(names)
