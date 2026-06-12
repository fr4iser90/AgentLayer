"""Cross-thread cancel propagation: parent agent run → embedded sub-agents."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_parent_cancel: dict[str, threading.Event] = {}


def register_parent_cancel(parent_run_id: str) -> None:
    """Register a cancel flag for a parent ``agent_run_id`` (chat / WS turn)."""
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        ev = _parent_cancel.get(rid)
        if ev is None:
            ev = threading.Event()
            _parent_cancel[rid] = ev


def unregister_parent_cancel(parent_run_id: str) -> None:
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        _parent_cancel.pop(rid, None)


def signal_parent_cancel(parent_run_id: str) -> None:
    """Signal all sub-agents listening on this parent run to stop."""
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        ev = _parent_cancel.get(rid)
    if ev is not None:
        ev.set()


def parent_cancel_event(parent_run_id: str) -> threading.Event | None:
    rid = (parent_run_id or "").strip()
    if not rid:
        return None
    with _lock:
        return _parent_cancel.get(rid)


def reset_parent_cancel_registry_for_tests() -> None:
    with _lock:
        _parent_cancel.clear()
