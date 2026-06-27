"""
Capability gate (ADR 0003): optional env allow/block/confirm lists applied at :func:`run_tool` time.

- **Blocked** capabilities always deny.
- **Allowed** (if non-empty): tool must declare at least one capability intersecting the allowlist.
  Tools with no declared capabilities are denied when an allowlist is active (strict governance).
- **Confirm**: tool needs capabilities in the confirm set; caller must list them in
  :func:`apps.domain.tools.invocation_context.get_capability_confirmed` (set by chat body
  ``agent_capability_confirm`` or HTTP header on ``/tools/run``).

Empty env lists = that dimension disabled (backward compatible).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from apps.backend.domain.plugin_system.capability_index import effective_capabilities_for_tool
from apps.backend.domain.tools.invocation_context import get_capability_confirmed

logger = logging.getLogger(__name__)


class CapabilityGovernanceDependencies(Protocol):
    def gate_sets(self) -> tuple[frozenset[str], frozenset[str], frozenset[str]]: ...


_deps: CapabilityGovernanceDependencies | None = None


def register_capability_governance_dependencies(deps: CapabilityGovernanceDependencies) -> None:
    global _deps
    _deps = deps


def _parse_csv_caps(raw: str | None) -> frozenset[str]:
    if not raw or not str(raw).strip():
        return frozenset()
    return frozenset(x.strip().lower() for x in str(raw).split(",") if x.strip())


def parse_user_capability_confirm(raw: Any) -> frozenset[str]:
    """
    Parse ``agent_capability_confirm`` (chat JSON) or equivalent: comma / list of ids.
    Normalized to lowercase so they match ``AGENT_CAPABILITY_GATE_*`` env lists.
    """
    if raw is None:
        return frozenset()
    if isinstance(raw, str):
        return frozenset(
            x.strip().lower() for x in raw.replace(",", " ").split() if x.strip()
        )
    if isinstance(raw, list):
        return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
    return frozenset()


def gate_sets() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """(allowed, blocked, confirm_required) — each may be empty."""
    return _deps.gate_sets() if _deps is not None else (frozenset(), frozenset(), frozenset())


def capability_gate_error_json(
    tool_name: str,
    meta: dict[str, Any] | None,
) -> str | None:
    """
    Return a JSON error string if this tool call must be blocked, else None.
    """
    allow, block, confirm = gate_sets()
    if not allow and not block and not confirm:
        return None

    caps = (
        effective_capabilities_for_tool(meta, tool_name)
        if meta
        else []
    )
    cap_lc = {c.lower() for c in caps}

    if block:
        hit = cap_lc & block
        if hit:
            return json.dumps(
                {
                    "ok": False,
                    "error": "capability blocked by operator policy",
                    "code": "capability_blocked",
                    "blocked_capabilities": sorted(hit),
                },
                ensure_ascii=False,
            )

    if allow:
        if not cap_lc:
            return json.dumps(
                {
                    "ok": False,
                    "error": "tool has no declared capabilities; denied under AGENT_CAPABILITY_GATE_ALLOW",
                    "code": "capability_unclassified",
                },
                ensure_ascii=False,
            )
        if not (cap_lc & allow):
            return json.dumps(
                {
                    "ok": False,
                    "error": "no tool capability matches AGENT_CAPABILITY_GATE_ALLOW",
                    "code": "capability_not_allowed",
                    "tool_capabilities": sorted(cap_lc),
                },
                ensure_ascii=False,
            )

    if confirm:
        need = cap_lc & confirm
        if need:
            ok = {x.lower() for x in get_capability_confirmed()}
            if not need.issubset(ok):
                return json.dumps(
                    {
                        "ok": False,
                        "error": "capability confirmation required for this tool",
                        "code": "capability_confirm_required",
                        "pending_capabilities": sorted(need),
                        "hint": (
                            "Send agent_capability_confirm in chat JSON listing these capability ids, "
                            "or X-Agent-Capability-Confirm header for /tools/run."
                        ),
                    },
                    ensure_ascii=False,
                )

    return None
