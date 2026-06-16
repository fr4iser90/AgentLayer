"""Per-request tenant/user identity for DB-scoped tools (set from HTTP headers)."""

from __future__ import annotations

import contextlib
import contextvars
import uuid
from typing import Any

_identity: contextvars.ContextVar[tuple[int, uuid.UUID | None] | None] = (
    contextvars.ContextVar("agent_identity", default=None)
)
_workspace: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("agent_workspace", default=None)
)
_benchmark_run_id: contextvars.ContextVar[uuid.UUID | None] = contextvars.ContextVar(
    "benchmark_run_id",
    default=None,
)
_harness_profile: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "harness_profile",
    default=None,
)
_llm_queue_source: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "llm_queue_source",
    default=None,
)


def set_identity(tenant_id: int, user_id: uuid.UUID) -> contextvars.Token:
    return _identity.set((tenant_id, user_id))


def get_identity() -> tuple[int, uuid.UUID | None]:
    """
    Current (tenant_id, user_id). If no request context set, returns (1, None).
    Callers that need a user for FK rows must require a non-None user_id themselves.
    """
    v = _identity.get()
    if v is None:
        return (1, None)
    return v


def set_workspace(workspace: dict[str, Any] | None) -> contextvars.Token:
    return _workspace.set(workspace)


def get_workspace() -> dict[str, Any] | None:
    """Current workspace dict with id, name, path, etc."""
    return _workspace.get()


def reset_workspace(token: contextvars.Token) -> None:
    _workspace.reset(token)


def reset_identity(token: contextvars.Token) -> None:
    _identity.reset(token)


def set_benchmark_run_id(run_id: uuid.UUID | None) -> contextvars.Token:
    return _benchmark_run_id.set(run_id)


def get_benchmark_run_id() -> uuid.UUID | None:
    return _benchmark_run_id.get()


def reset_benchmark_run_id(token: contextvars.Token) -> None:
    _benchmark_run_id.reset(token)


def set_harness_profile(
    catalog_owned_by: str | None,
    model: str | None,
) -> contextvars.Token:
    catalog = str(catalog_owned_by or "").strip()
    mid = str(model or "").strip()
    if catalog:
        return _harness_profile.set((catalog, mid))
    return _harness_profile.set(None)


def get_harness_profile() -> tuple[str, str] | None:
    return _harness_profile.get()


def reset_harness_profile(token: contextvars.Token) -> None:
    _harness_profile.reset(token)


def set_llm_queue_source(source: str | None) -> contextvars.Token:
    s = (source or "").strip().lower() or None
    return _llm_queue_source.set(s)


def get_llm_queue_source() -> str | None:
    return _llm_queue_source.get()


def reset_llm_queue_source(token: contextvars.Token) -> None:
    _llm_queue_source.reset(token)


@contextlib.contextmanager
def llm_queue_source_scope(source: str | None):
    tok = set_llm_queue_source(source)
    try:
        yield
    finally:
        reset_llm_queue_source(tok)
