"""Ports for plugin registry runtime dependencies."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class PluginRegistryDependencies:
    def tool_scan_directories(self) -> list[Path]:
        return []

    def tools_allowed_sha256(self) -> frozenset[str] | None:
        return None

    def tools_extra_dir(self) -> str:
        return ""

    def effective_domain_order(self) -> list[str]:
        return []

    def overlay_phrases_for_domain(self, domain: str) -> list[str]:
        return []

    def log_tool_invocation(
        self,
        name: str,
        arguments: dict[str, Any],
        result: str,
        ok: bool,
        *,
        agent_run_id: Any = None,
    ) -> None:
        return None


_deps: PluginRegistryDependencies = PluginRegistryDependencies()


def register_plugin_registry_dependencies(deps: PluginRegistryDependencies) -> None:
    global _deps
    _deps = deps


def plugin_registry_dependencies() -> PluginRegistryDependencies:
    return _deps


def tool_scan_directories() -> list[Path]:
    return _deps.tool_scan_directories()


def tools_allowed_sha256() -> frozenset[str] | None:
    return _deps.tools_allowed_sha256()


def tools_extra_dir() -> str:
    return _deps.tools_extra_dir()
