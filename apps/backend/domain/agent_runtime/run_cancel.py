"""Cross-thread cancel propagation: root agent run -> all embedded/nested sub-agents."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_parent_cancel: dict[str, threading.Event] = {}
_run_to_root: dict[str, str] = {}


def _resolve_root(run_id: str) -> str:
    rid = (run_id or "").strip()
    if not rid:
        return ""
    return _run_to_root.get(rid, rid)


def register_parent_cancel(parent_run_id: str) -> None:
    """Register a cancel flag for a root ``agent_run_id`` (chat / WS turn)."""
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        ev = _parent_cancel.get(rid)
        if ev is None:
            ev = threading.Event()
            _parent_cancel[rid] = ev
        _run_to_root[rid] = rid


def link_run_to_cancel_root(run_id: str, parent_run_id: str) -> None:
    """Link a child run to the cancel root of its parent (General -> delegate -> task ...)."""
    rid = (run_id or "").strip()
    parent = (parent_run_id or "").strip()
    if not rid or not parent:
        return
    with _lock:
        root = _resolve_root(parent)
        if not root:
            root = parent
        _run_to_root[rid] = root
        if root not in _parent_cancel:
            _parent_cancel[root] = threading.Event()


def unregister_parent_cancel(parent_run_id: str) -> None:
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        _parent_cancel.pop(rid, None)
        stale = [k for k, v in _run_to_root.items() if k == rid or v == rid]
        for k in stale:
            _run_to_root.pop(k, None)


def signal_parent_cancel(parent_run_id: str) -> None:
    """Signal all sub-agents in the tree rooted at this run to stop."""
    rid = (parent_run_id or "").strip()
    if not rid:
        return
    with _lock:
        root = _resolve_root(rid)
        ev = _parent_cancel.get(root) if root else None
    if ev is not None:
        ev.set()


def root_cancel_event(for_run_id: str) -> threading.Event | None:
    """Cancel event for the root of ``for_run_id``'s tree (or the run itself if unlinked)."""
    rid = (for_run_id or "").strip()
    if not rid:
        return None
    with _lock:
        root = _resolve_root(rid)
        return _parent_cancel.get(root) if root else None


def parent_cancel_event(parent_run_id: str) -> threading.Event | None:
    """Backward-compatible alias for ``root_cancel_event``."""
    return root_cancel_event(parent_run_id)


def registered_parent_run_ids() -> frozenset[str]:
    """Root agent_run_ids with a live worker (in-memory cancel registry)."""
    with _lock:
        return frozenset(_parent_cancel)


def reset_parent_cancel_registry_for_tests() -> None:
    with _lock:
        _parent_cancel.clear()
        _run_to_root.clear()
