"""Normalize per-job schedule notification settings."""

from __future__ import annotations

from typing import Any

NOTIFY_ON_VALUES = frozenset({"never", "failure", "always"})
NOTIFY_CHANNEL_VALUES = frozenset({"in_app", "telegram", "discord"})
DEFAULT_NOTIFY_ON = "always"
DEFAULT_NOTIFY_CHANNELS: tuple[str, ...] = ("in_app",)


def normalize_notify_on(raw: Any, *, default: str = DEFAULT_NOTIFY_ON) -> str:
    s = str(raw or "").strip().lower()
    if s in NOTIFY_ON_VALUES:
        return s
    return default if default in NOTIFY_ON_VALUES else DEFAULT_NOTIFY_ON


def require_notify_on(raw: Any) -> str | None:
    """Return normalized value, ``None`` if omitted, or raise ``ValueError`` if invalid."""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    if s not in NOTIFY_ON_VALUES:
        raise ValueError("notify_on must be never, failure, or always")
    return s


def normalize_notify_channels(raw: Any, *, default: tuple[str, ...] | None = None) -> list[str]:
    """Return ordered unique channels; empty input → default (usually ``in_app``)."""
    fallback = list(default if default is not None else DEFAULT_NOTIFY_CHANNELS)
    if raw is None:
        return fallback
    items: list[Any]
    if isinstance(raw, str):
        items = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return fallback
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        ch = str(item or "").strip().lower()
        if ch not in NOTIFY_CHANNEL_VALUES or ch in seen:
            continue
        seen.add(ch)
        out.append(ch)
    return out if out else fallback


def should_notify_for_outcome(*, notify_on: str, success: bool) -> bool:
    mode = normalize_notify_on(notify_on)
    if mode == "never":
        return False
    if mode == "failure":
        return not success
    return True  # always
