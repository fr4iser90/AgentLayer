"""Dispatch tool calls by name (chat loop, tests, and :mod:`app.plugin_invoke`)."""

from __future__ import annotations

import json
import os
from contextvars import ContextVar, Token

from apps.backend.domain.plugin_system.registry import get_registry

__all__ = ["run_tool"]

_chain_depth: ContextVar[int] = ContextVar("agent_tool_chain_depth", default=0)


def _max_chain_depth() -> int:
    raw = (os.environ.get("AGENT_TOOL_CHAIN_MAX_DEPTH") or "").strip()
    if not raw:
        return 24
    try:
        n = int(raw)
    except ValueError:
        return 24
    return max(1, min(256, n))


def run_tool(name: str, arguments: dict, context: dict | None = None) -> str:
    """
    Run a registered handler. Nested calls (plugin → other tool) increment a context
    depth counter; exceeding :envvar:`AGENT_TOOL_CHAIN_MAX_DEPTH` returns JSON error.
    
    Args:
        name: Tool name
        arguments: Tool arguments
        context: Context dict passed to tool (NOT imported by tool!)
    """
    depth = _chain_depth.get()
    limit = _max_chain_depth()
    if depth >= limit:
        return json.dumps(
            {
                "ok": False,
                "error": f"tool chain depth exceeded ({limit}); avoid recursive tool calls",
            },
            ensure_ascii=False,
        )
    token: Token[int] | None = None
    try:
        token = _chain_depth.set(depth + 1)
        reg = get_registry()
        nm = (name or "").strip()
        if nm.startswith("mcp__"):
            from apps.backend.infrastructure.mcp_runtime import mcp_invoke_tool_sync

            return mcp_invoke_tool_sync(nm, dict(arguments or {}))
        meta = reg.meta_entry_for_tool_name(nm) if nm else None
        if meta:
            from apps.backend.domain.identity import get_identity
            from apps.backend.domain.plugin_system.tool_policy import (
                caller_fulfills_effective_policy,
                effective_flags,
                manifest_execution_context,
            )
            from apps.backend.infrastructure.db import db as _db

            try:
                from apps.backend.infrastructure.tool_operator_policy_db import policies_map

                pmap = policies_map()
            except Exception:
                pmap = {}
            eff = effective_flags(meta, nm, pmap)
            if not eff["enabled"]:
                return json.dumps(
                    {"ok": False, "error": "tool disabled by operator policy"},
                    ensure_ascii=False,
                )
            tid, uid = get_identity()
            if not caller_fulfills_effective_policy(_db.user_role(uid), int(tid), eff):
                return json.dumps(
                    {
                        "ok": False,
                        "error": "tool not allowed for this user role or tenant",
                    },
                    ensure_ascii=False,
                )
            man_ctx = manifest_execution_context(meta, nm)
            if man_ctx == "host" and eff["execution_context"] == "container":
                return json.dumps(
                    {
                        "ok": False,
                        "error": (
                            "tool manifest requires host-class execution; effective policy "
                            "is container — adjust AGENT_MODE / Interfaces or disable the tool"
                        ),
                    },
                    ensure_ascii=False,
                )
            from apps.backend.domain.plugin_system.capability_governance import (
                capability_gate_error_json,
            )

            gate_err = capability_gate_error_json(nm, meta)
            if gate_err:
                return gate_err
        return reg.run_tool(name, arguments, context=context)
    finally:
        if token is not None:
            _chain_depth.reset(token)
