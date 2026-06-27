"""Infrastructure adapter for plugin tool runtime checks."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.plugin_system import tools as domain
from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.mcp_runtime import mcp_invoke_tool_sync
from apps.backend.infrastructure.tool_operator_policy_db import policies_map


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


domain.register_tool_runtime_dependencies(_ToolRuntimeDeps())

run_tool = domain.run_tool
