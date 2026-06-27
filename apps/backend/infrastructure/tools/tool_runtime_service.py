"""Infrastructure adapter for plugin tool runtime checks."""

from __future__ import annotations

import os
from typing import Any

from apps.backend.domain.plugin_system import capability_governance
from apps.backend.domain.plugin_system import tools as domain
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.plugins.mcp_runtime import mcp_invoke_tool_sync
from apps.backend.infrastructure.tools.tool_operator_policy_db import policies_map


class _ToolRuntimeDeps:
    @staticmethod
    def mcp_invoke_tool_sync(name: str, arguments: dict[str, Any]) -> str:
        return mcp_invoke_tool_sync(name, arguments)

    @staticmethod
    def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
        return policies_map()

    @staticmethod
    def user_role(user_id: Any) -> str:
        return db.user_role(user_id)

    @staticmethod
    def max_chain_depth() -> int:
        raw = (os.environ.get("AGENT_TOOL_CHAIN_MAX_DEPTH") or "").strip()
        if not raw:
            return 24
        try:
            value = int(raw)
        except ValueError:
            return 24
        return max(1, min(256, value))


class _CapabilityGovernanceDeps:
    @staticmethod
    def _parse(raw: str) -> frozenset[str]:
        return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())

    def gate_sets(self) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
        return (
            self._parse(os.environ.get("AGENT_CAPABILITY_GATE_ALLOW") or ""),
            self._parse(os.environ.get("AGENT_CAPABILITY_GATE_BLOCK") or ""),
            self._parse(os.environ.get("AGENT_CAPABILITY_GATE_CONFIRM") or ""),
        )


domain.register_tool_runtime_dependencies(_ToolRuntimeDeps())
capability_governance.register_capability_governance_dependencies(_CapabilityGovernanceDeps())

run_tool = domain.run_tool
