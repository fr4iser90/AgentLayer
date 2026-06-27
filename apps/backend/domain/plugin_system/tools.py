"""Dispatch tool calls by name (chat loop, tests, and :mod:`app.plugin_invoke`)."""

from __future__ import annotations

import json
from contextvars import ContextVar, Token
from typing import Any, Protocol

from apps.backend.domain.plugin_system.registry import get_registry

__all__ = ["run_tool"]

_chain_depth: ContextVar[int] = ContextVar("agent_tool_chain_depth", default=0)


class ToolRuntimeDependencies(Protocol):
    def mcp_invoke_tool_sync(self, name: str, arguments: dict[str, Any]) -> str: ...

    def policies_map(self) -> dict[tuple[str, str], dict[str, Any]]: ...

    def user_role(self, user_id: Any) -> str: ...

    def max_chain_depth(self) -> int: ...


_deps: ToolRuntimeDependencies | None = None


def register_tool_runtime_dependencies(deps: ToolRuntimeDependencies) -> None:
    global _deps
    _deps = deps


def mcp_invoke_tool_sync(name: str, arguments: dict[str, Any]) -> str:
    if _deps is None:
        return json.dumps({"ok": False, "error": "MCP runtime not configured"}, ensure_ascii=False)
    return _deps.mcp_invoke_tool_sync(name, arguments)


def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
    return _deps.policies_map() if _deps is not None else {}


def user_role(user_id: Any) -> str:
    return _deps.user_role(user_id) if _deps is not None else ""


def _max_chain_depth() -> int:
    return _deps.max_chain_depth() if _deps is not None else 24


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
            return mcp_invoke_tool_sync(nm, dict(arguments or {}))
        meta = reg.meta_entry_for_tool_name(nm) if nm else None
        if meta:
            from apps.backend.domain.shared.identity import get_identity
            from apps.backend.domain.plugin_system.tool_policy import (
                caller_fulfills_effective_policy,
                effective_flags,
                manifest_execution_context,
            )
            pmap = policies_map()
            eff = effective_flags(meta, nm, pmap)
            if not eff["enabled"]:
                return json.dumps(
                    {"ok": False, "error": "tool disabled by operator policy"},
                    ensure_ascii=False,
                )
            tid, uid = get_identity()
            if not caller_fulfills_effective_policy(user_role(uid), int(tid), eff):
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
