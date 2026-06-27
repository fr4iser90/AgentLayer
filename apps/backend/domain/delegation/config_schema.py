"""Validate and normalize User / Workspace Delegate configuration JSON."""

from __future__ import annotations

import copy
import json
from typing import Any

MAX_USER_CONFIG_BYTES = 8192
MAX_WORKSPACE_CONFIG_BYTES = 4096
MAX_NOTES_CHARS = 2000
MAX_GOALS = 50
MAX_GOAL_CHARS = 500
MAX_PRIORITIES = 8

_LEVELS = frozenset({"low", "medium", "high"})
_PRIORITY_TOKENS = frozenset({"security", "stability", "maintainability", "speed"})
_PRIMARY_GOALS = _PRIORITY_TOKENS

DEFAULT_DELEGATE_CONFIG: dict[str, Any] = {
    "communication": {
        "directness": "medium",
        "detail_level": "medium",
        "ask_before_major_changes": True,
    },
    "engineering": {
        "security_first": True,
        "prefer_tests": True,
        "prefer_refactoring": False,
        "primary_goal": "stability",
        "priorities": ["security", "stability", "maintainability", "speed"],
    },
    "autonomy": {
        "can_fix_minor_issues": True,
        "can_merge_prs": False,
        "can_force_push": False,
    },
    "decisioning": {
        "risk_tolerance": "low",
    },
    "escalation": {
        "ask_on_production_changes": True,
        "ask_on_database_migrations": True,
        "ask_on_security_findings": False,
    },
    "goals": [],
}

DEFAULT_USER_DELEGATE_CONFIG: dict[str, Any] = copy.deepcopy(DEFAULT_DELEGATE_CONFIG)

DEFAULT_WORKSPACE_DELEGATE_CONFIG: dict[str, Any] = copy.deepcopy(DEFAULT_DELEGATE_CONFIG)
# Workspace overlay may default slightly higher appetite when only workspace row exists.
DEFAULT_WORKSPACE_DELEGATE_CONFIG["decisioning"]["risk_tolerance"] = "medium"


def default_delegate_config(*, scope: str = "user") -> dict[str, Any]:
    if scope == "workspace":
        return copy.deepcopy(DEFAULT_WORKSPACE_DELEGATE_CONFIG)
    return copy.deepcopy(DEFAULT_USER_DELEGATE_CONFIG)


def _norm_level(raw: Any, *, default: str = "medium") -> str:
    s = str(raw or default).strip().lower()
    return s if s in _LEVELS else default


def _norm_bool(raw: Any, *, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    return bool(raw)


def _norm_primary_goal(raw: Any, *, default: str) -> str:
    s = str(raw or default).strip().lower()
    return s if s in _PRIMARY_GOALS else default


def _norm_priorities(raw: Any, *, default: list[str]) -> list[str]:
    if raw is None:
        return list(default)
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.replace(";", ",").split(",") if x.strip()]
    if not isinstance(raw, list):
        raise ValueError("priorities must be a list of tokens")
    out: list[str] = []
    seen: set[str] = set()
    for item in raw[:MAX_PRIORITIES]:
        tok = str(item).strip().lower()
        if tok not in _PRIORITY_TOKENS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out if out else list(default)


def _norm_goals(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not isinstance(raw, list):
        raise ValueError("goals must be a list of strings")
    out: list[str] = []
    for item in raw[:MAX_GOALS]:
        s = str(item).strip()
        if not s:
            continue
        if len(s) > MAX_GOAL_CHARS:
            s = s[:MAX_GOAL_CHARS]
        out.append(s)
    return out


def normalize_delegate_config(raw: Any, *, scope: str = "user") -> dict[str, Any]:
    """Return a deep copy of validated delegate config. ``scope`` is ``user`` or ``workspace``."""
    if raw is None:
        return default_delegate_config(scope=scope)
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")

    base = default_delegate_config(scope=scope)
    comm = raw.get("communication") if isinstance(raw.get("communication"), dict) else {}
    eng = raw.get("engineering") if isinstance(raw.get("engineering"), dict) else {}
    aut = raw.get("autonomy") if isinstance(raw.get("autonomy"), dict) else {}
    dec = raw.get("decisioning") if isinstance(raw.get("decisioning"), dict) else {}
    esc = raw.get("escalation") if isinstance(raw.get("escalation"), dict) else {}

    out: dict[str, Any] = {
        "communication": {
            "directness": _norm_level(comm.get("directness"), default=base["communication"]["directness"]),
            "detail_level": _norm_level(comm.get("detail_level"), default=base["communication"]["detail_level"]),
            "ask_before_major_changes": _norm_bool(
                comm.get("ask_before_major_changes"),
                default=base["communication"]["ask_before_major_changes"],
            ),
        },
        "engineering": {
            "security_first": _norm_bool(eng.get("security_first"), default=base["engineering"]["security_first"]),
            "prefer_tests": _norm_bool(eng.get("prefer_tests"), default=base["engineering"]["prefer_tests"]),
            "prefer_refactoring": _norm_bool(
                eng.get("prefer_refactoring"),
                default=base["engineering"]["prefer_refactoring"],
            ),
            "primary_goal": _norm_primary_goal(
                eng.get("primary_goal"),
                default=base["engineering"]["primary_goal"],
            ),
            "priorities": _norm_priorities(
                eng.get("priorities"),
                default=base["engineering"]["priorities"],
            ),
        },
        "autonomy": {
            "can_fix_minor_issues": _norm_bool(
                aut.get("can_fix_minor_issues"),
                default=base["autonomy"]["can_fix_minor_issues"],
            ),
            "can_merge_prs": _norm_bool(aut.get("can_merge_prs"), default=base["autonomy"]["can_merge_prs"]),
            "can_force_push": _norm_bool(aut.get("can_force_push"), default=base["autonomy"]["can_force_push"]),
        },
        "decisioning": {
            "risk_tolerance": _norm_level(
                dec.get("risk_tolerance"),
                default=base["decisioning"]["risk_tolerance"],
            ),
        },
        "escalation": {
            "ask_on_production_changes": _norm_bool(
                esc.get("ask_on_production_changes"),
                default=base["escalation"]["ask_on_production_changes"],
            ),
            "ask_on_database_migrations": _norm_bool(
                esc.get("ask_on_database_migrations"),
                default=base["escalation"]["ask_on_database_migrations"],
            ),
            "ask_on_security_findings": _norm_bool(
                esc.get("ask_on_security_findings"),
                default=base["escalation"]["ask_on_security_findings"],
            ),
        },
        "goals": _norm_goals(raw.get("goals")),
    }

    max_bytes = MAX_WORKSPACE_CONFIG_BYTES if scope == "workspace" else MAX_USER_CONFIG_BYTES
    encoded = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > max_bytes:
        raise ValueError(f"delegate config too large (max {max_bytes} bytes serialized)")

    return out


def normalize_delegate_notes(raw: Any) -> str:
    s = str(raw or "").strip()
    if len(s) > MAX_NOTES_CHARS:
        raise ValueError(f"notes too long (max {MAX_NOTES_CHARS} chars)")
    return s


def public_delegate_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "config": default_delegate_config(scope="user"),
            "notes": "",
            "updated_at": None,
        }
    cfg = normalize_delegate_config(row.get("config"), scope="user")
    return {
        "config": cfg,
        "notes": normalize_delegate_notes(row.get("notes") or ""),
        "updated_at": row.get("updated_at"),
    }
