"""ADR 0009 index consent: stored workspace tier, operator cap, effective min of the two.

The laptop cannot dump an index just because it holds an API key. Owner/editor HTTP is the
gate for PATCH and upload; this module is the second gate: the operator's ceiling, and the
refusal copy that names both the workspace value and the cap.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apps.backend.infrastructure.workspace.workspace_columns import (
    CLIENT_EXECUTION,
    normalize_execution_mode,
)

logger = logging.getLogger(__name__)

INDEX_CONSENT_NONE = "none"
INDEX_CONSENT_SYMBOLS = "symbols"
INDEX_CONSENT_TEXT = "text"
INDEX_CONSENT_VALUES = (INDEX_CONSENT_NONE, INDEX_CONSENT_SYMBOLS, INDEX_CONSENT_TEXT)

_RANK = {
    INDEX_CONSENT_NONE: 0,
    INDEX_CONSENT_SYMBOLS: 1,
    INDEX_CONSENT_TEXT: 2,
}

_CAP_CACHE: tuple[float, str] | None = None
_CAP_TTL_SEC = 2.0


def normalize_index_consent(raw: Any) -> str | None:
    v = str(raw or "").strip().lower()
    return v if v in _RANK else None


def consent_rank(raw: Any) -> int:
    n = normalize_index_consent(raw)
    return _RANK[n] if n else 0


def consent_covers(have: Any, needed: Any) -> bool:
    return consent_rank(have) >= consent_rank(needed)


def default_index_consent_for_mode(execution_mode: Any) -> str:
    if normalize_execution_mode(execution_mode) == CLIENT_EXECUTION:
        return INDEX_CONSENT_NONE
    return INDEX_CONSENT_TEXT


def stored_index_consent(workspace: dict[str, Any] | None) -> str:
    ws = workspace or {}
    n = normalize_index_consent(ws.get("index_consent"))
    if n:
        return n
    return default_index_consent_for_mode(ws.get("execution_mode"))


def operator_index_consent_max() -> str:
    """Operator ceiling, then env, then ``text``. Cached briefly; missing column is not fatal."""
    global _CAP_CACHE
    now = time.monotonic()
    if _CAP_CACHE is not None and now - _CAP_CACHE[0] < _CAP_TTL_SEC:
        return _CAP_CACHE[1]
    value = _read_operator_cap()
    _CAP_CACHE = (now, value)
    return value


def invalidate_index_consent_cap_cache() -> None:
    global _CAP_CACHE
    _CAP_CACHE = None


def _env_cap() -> str:
    import os

    n = normalize_index_consent(os.environ.get("AGENT_WORKSPACE_INDEX_CONSENT_MAX"))
    return n or INDEX_CONSENT_TEXT


def _read_operator_cap() -> str:
    try:
        from apps.backend.infrastructure.db import db

        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_index_consent_max FROM operator_settings WHERE id = 1"
                )
                row = cur.fetchone()
            conn.commit()
        if row:
            n = normalize_index_consent(row[0])
            if n:
                return n
    except Exception as exc:
        logger.debug("operator_index_consent_max: %s", exc)
    return _env_cap()


def clamp_index_consent(requested: str) -> str:
    """``min(requested, operator max)`` — used at create so a new server row cannot exceed the cap."""
    req = normalize_index_consent(requested) or INDEX_CONSENT_NONE
    cap = operator_index_consent_max()
    return req if consent_covers(cap, req) else cap


def refuse_if_above_operator_cap(requested: Any) -> str | None:
    """User PATCH: refuse rather than silently clamp, so the operator decision is visible."""
    req = normalize_index_consent(requested)
    if req is None:
        return "index_consent must be none, symbols, or text"
    cap = operator_index_consent_max()
    if not consent_covers(cap, req):
        return f"operator cap is {cap}; cannot set index_consent={req}"
    return None


def effective_index_consent(workspace: dict[str, Any] | None) -> str:
    stored = stored_index_consent(workspace)
    cap = operator_index_consent_max()
    return stored if consent_covers(cap, stored) else cap


def consent_refusal(workspace: dict[str, Any] | None, needed: str) -> str | None:
    need = normalize_index_consent(needed) or INDEX_CONSENT_TEXT
    have = effective_index_consent(workspace)
    if consent_covers(have, need):
        return None
    cap = operator_index_consent_max()
    stored = stored_index_consent(workspace)
    return (
        f"This action needs index_consent={need} "
        f"(workspace consent is {stored}, operator cap is {cap})."
    )


def mode_needs_consent(mode: str) -> str:
    """What ``POST /index`` with this crawl mode requires. ``code`` is symbols; ``docs``/``full`` are text."""
    m = (mode or "full").strip().lower()
    if m == "code":
        return INDEX_CONSENT_SYMBOLS
    return INDEX_CONSENT_TEXT


def sanitize_upload_rel_path(raw: Any) -> str | None:
    """Relative posix path for client uploads. Absolute, ``~``, ``..``, and drive letters are refused."""
    r = str(raw or "").strip().replace("\\", "/")
    if not r or r in (".",):
        return None
    if r.startswith("/") or r.startswith("~") or "\0" in r:
        return None
    if len(r) >= 2 and r[1] == ":":
        return None
    parts = [p for p in r.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    out = "/".join(parts)
    if len(out) > 1024:
        return None
    return out
