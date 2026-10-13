"""Port: run an agent turn inside an **external** agent runtime process.

AgentLayer's own planner loop (``application/agent_runtime/use_cases/chat_tool_loop.py``)
is one runtime for an agent turn. This port makes a second kind possible: a coding agent
that ships as its own binary (Qwen Code, and later others) while AgentLayer keeps
ownership of identity, workspace authorization, streaming, cancellation and audit.

Domain layer only: contracts plus an in-process registry. No I/O, no provider access,
no subprocess. Adapters live in
``apps/backend/infrastructure/agent_runtime/external_runtimes/`` and register themselves
at import time (same wiring pattern as ``domain/agent_runtime/registry.py``).

An agent selects a runtime by declaring ``external_runtime: <id>`` in
``plugins/agents/<id>/agent.yaml``; nothing else in the chat path knows which vendor
is underneath.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

logger = logging.getLogger(__name__)

#: Normalized stream events every adapter must produce. Adapters never emit
#: AgentLayer WebSocket payloads directly — see ``external_runtime_events``.
EventKind = Literal["status", "delta", "tool_call", "tool_result", "done", "error"]

#: Permission modes, ordered by blast radius. Adapters map these onto vendor names.
PERMISSION_PLAN = "plan"
PERMISSION_AUTO_EDIT = "auto-edit"
PERMISSION_YOLO = "yolo"

PERMISSION_ORDER: tuple[str, ...] = (PERMISSION_PLAN, PERMISSION_AUTO_EDIT, PERMISSION_YOLO)


@dataclass(frozen=True)
class ExternalRunRequest:
    """Everything an external process needs, resolved by AgentLayer beforehand.

    ``workspace_path`` is already authorized and confined (see
    ``application/agent_runtime/use_cases/chat_run_bootstrap.py``); adapters must not
    re-resolve workspaces or widen the path.
    """

    task: str
    workspace_path: str
    agent_id: str
    runtime_id: str
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    permission_mode: str = PERMISSION_AUTO_EDIT
    max_turns: int | None = None
    resume_session_id: str | None = None
    append_system_prompt: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    timeout_sec: int = 1800
    conversation_id: str | None = None
    user_id: str | None = None
    exclude_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExternalRuntimeEvent:
    """One normalized progress event from the external runtime."""

    kind: EventKind
    text: str = ""
    tool: str | None = None
    call_id: str | None = None
    args_preview: str | None = None
    ok: bool = True
    error: str | None = None
    session_id: str | None = None
    usage: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ExternalRunResult:
    """Terminal outcome of one external run.

    ``session_id`` is the *vendor-native* id used to resume the same session on the
    next turn of the same conversation; AgentLayer stores it, adapters stay stateless.
    """

    ok: bool
    text: str = ""
    session_id: str | None = None
    changed_files: tuple[str, ...] = ()
    no_vcs: bool = False
    usage: Mapping[str, Any] | None = None
    error: str | None = None
    exit_code: int | None = None


EventSink = Callable[[ExternalRuntimeEvent], Awaitable[None]]


class ExternalAgentRuntime(Protocol):
    """A coding-agent runtime that runs outside AgentLayer's planner loop."""

    #: Stable identifier referenced from ``agent.yaml`` as ``external_runtime``.
    id: str
    supports_resume: bool
    supports_write: bool
    default_permission_mode: str

    def available(self) -> tuple[bool, str]:
        """Return ``(usable, reason)``. ``reason`` is shown to the user when unusable.

        Must be cheap and must never raise: an uninstalled binary has to leave the
        rest of the product untouched.
        """
        ...

    async def run(
        self,
        request: ExternalRunRequest,
        *,
        emit: EventSink,
        cancel_event: asyncio.Event | None = None,
    ) -> ExternalRunResult:
        """Stream progress through ``emit`` until the run finishes.

        Must honour ``cancel_event`` (abort the child, return ``ok=False`` with
        ``error="cancelled"``) and ``request.timeout_sec``.
        """
        ...


_REGISTRY: dict[str, ExternalAgentRuntime] = {}


def register_external_runtime(runtime: ExternalAgentRuntime) -> None:
    """Register an adapter under ``runtime.id``; re-registering replaces it (reload-safe)."""
    runtime_id = str(getattr(runtime, "id", "") or "").strip()
    if not runtime_id:
        logger.warning("external runtime without id ignored: %r", runtime)
        return
    _REGISTRY[runtime_id] = runtime


def unregister_external_runtime(runtime_id: str) -> None:
    _REGISTRY.pop(str(runtime_id or "").strip(), None)


def get_external_runtime(runtime_id: str) -> ExternalAgentRuntime | None:
    return _REGISTRY.get(str(runtime_id or "").strip())


def available_external_runtimes() -> list[dict[str, Any]]:
    """Catalog for ``GET /v1/chat/runtime`` and operator diagnostics."""
    out: list[dict[str, Any]] = []
    for runtime_id in sorted(_REGISTRY):
        runtime = _REGISTRY[runtime_id]
        usable, reason = _safe_available(runtime)
        out.append(
            {
                "id": runtime_id,
                "available": usable,
                "reason": reason,
                "supports_resume": bool(getattr(runtime, "supports_resume", False)),
                "supports_write": bool(getattr(runtime, "supports_write", False)),
                "default_permission_mode": str(
                    getattr(runtime, "default_permission_mode", PERMISSION_AUTO_EDIT)
                ),
            }
        )
    return out


def resolve_external_runtime(runtime_id: str) -> tuple[ExternalAgentRuntime | None, str]:
    """Resolve a runtime for an agent turn: ``(runtime, reason_when_missing)``."""
    wanted = str(runtime_id or "").strip()
    if not wanted:
        return None, "no external_runtime declared"
    runtime = _REGISTRY.get(wanted)
    if runtime is None:
        known = ", ".join(sorted(_REGISTRY)) or "none registered"
        return None, f"unknown external_runtime {wanted!r} (registered: {known})"
    usable, reason = _safe_available(runtime)
    if not usable:
        return None, f"external runtime {wanted!r} unavailable: {reason}"
    return runtime, ""


def clamp_permission_mode(requested: str, ceiling: str) -> str:
    """Never grant a mode wider than the operator ceiling (``AGENT_EXTERNAL_RUNTIME_ALLOW_YOLO``)."""
    req = str(requested or "").strip().lower()
    cap = str(ceiling or "").strip().lower()
    if req not in PERMISSION_ORDER:
        req = PERMISSION_AUTO_EDIT
    if cap not in PERMISSION_ORDER:
        cap = PERMISSION_AUTO_EDIT
    return req if PERMISSION_ORDER.index(req) <= PERMISSION_ORDER.index(cap) else cap


def _safe_available(runtime: ExternalAgentRuntime) -> tuple[bool, str]:
    try:
        usable, reason = runtime.available()
    except Exception as exc:  # availability probing must never break a request
        logger.warning("external runtime %s availability check failed", getattr(runtime, "id", "?"), exc_info=True)
        return False, f"availability check failed: {exc}"
    return bool(usable), str(reason or "")


__all__ = [
    "EventKind",
    "EventSink",
    "ExternalAgentRuntime",
    "ExternalRunRequest",
    "ExternalRunResult",
    "ExternalRuntimeEvent",
    "PERMISSION_AUTO_EDIT",
    "PERMISSION_ORDER",
    "PERMISSION_PLAN",
    "PERMISSION_YOLO",
    "available_external_runtimes",
    "clamp_permission_mode",
    "get_external_runtime",
    "register_external_runtime",
    "resolve_external_runtime",
    "unregister_external_runtime",
]
