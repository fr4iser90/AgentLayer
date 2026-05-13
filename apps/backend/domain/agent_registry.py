"""Agent Registry - dynamically loads agent plugins and manages tool mappings."""

from __future__ import annotations

import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any

from apps.backend.core.config import config, PLUGINS_DIR

logger = logging.getLogger(__name__)

DEFAULT_AGENT_PLUGINS_DIR = PLUGINS_DIR / "agents"

AGENT_TOOL_MAP = {
    "general": [
        "workspace.*",
        "knowledge.*",
        "productivity.*",
    ],
    "coding": [
        "coding.*",
        "create_tool",
        "replace_tool",
        "update_tool",
        "read_tool",
        "rename_tool",
        "list_tools",
        "get_tool_help",
        "project_explain",
    ],
    "operator": [
        "list_tools",
        "list_available_tools",
        "list_tool_categories",
        "list_tools_in_category",
        "get_tool_help",
        "read_tool",
        "rag_search",
        "schedule_job_list",
        "schedule_job_create",
        "schedule_job_set_enabled",
    ],
}


def _match_tool(tool_name: str, patterns: list[str]) -> bool:
    """Check if tool_name matches any pattern in the list."""
    for pattern in patterns:
        if pattern == tool_name:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if tool_name.startswith(prefix):
                return True
    return False


def _get_tools_for_agent(agent_id: str, all_tool_names: list[str]) -> list[str]:
    """Get tool names for a specific agent based on AGENT_TOOL_MAP."""
    patterns = AGENT_TOOL_MAP.get(agent_id, [])
    if not patterns:
        logger.warning("no tool patterns defined for agent %s, returning empty list", agent_id)
        return []
    
    matched = []
    for tool_name in all_tool_names:
        if _match_tool(tool_name, patterns):
            matched.append(tool_name)
    
    return matched


class AgentRegistry:
    """Registry that loads agent plugins and manages tool mappings."""

    def __init__(self) -> None:
        self._agents: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def _load_agents(self) -> None:
        """Scan plugin directories and load all agent definitions."""
        plugins_dirs = self._get_plugins_dirs()
        seen_ids: set[str] = set()

        for plugins_dir in plugins_dirs:
            if not plugins_dir.is_dir():
                logger.warning("plugins directory not found: %s", plugins_dir)
                continue

            for py_file in plugins_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue

                try:
                    self._load_agent_from_file(py_file, seen_ids)
                except Exception as e:
                    logger.warning("failed to load agent from %s: %s", py_file, e)

        if "general" not in self._agents:
            logger.warning("no general agent loaded, creating default")
            self._create_default_general_agent()

        logger.info("agent registry loaded: %d agents", len(self._agents))

    def _get_plugins_dirs(self) -> list[Path]:
        """Get list of directories to scan for agent plugins."""
        dirs = [DEFAULT_AGENT_PLUGINS_DIR]

        env_dirs = os.environ.get("AGENT_PLUGINS_DIR", "").strip()
        if env_dirs:
            for d in env_dirs.split(","):
                p = Path(d.strip())
                if p.is_dir():
                    dirs.append(p)

        return dirs

    def _load_agent_from_file(self, py_file: Path, seen_ids: set[str]) -> None:
        """Load agent definition from a Python file."""
        spec = importlib.util.spec_from_file_location(f"agent_{py_file.stem}", py_file)
        if spec is None or spec.loader is None:
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        agent_id = getattr(module, "AGENT_ID", None)
        if not agent_id:
            logger.debug("no AGENT_ID found in %s", py_file.name)
            return

        if agent_id in seen_ids:
            logger.warning("duplicate agent_id %s in %s, skipping", agent_id, py_file.name)
            return

        seen_ids.add(agent_id)

        definition = {
            "id": agent_id,
            "name": getattr(module, "AGENT_NAME", agent_id),
            "icon": getattr(module, "AGENT_ICON", "🤖"),
            "description": getattr(module, "AGENT_DESCRIPTION", ""),
            "system_prompt": getattr(module, "AGENT_SYSTEM_PROMPT", ""),
            "tool_domain": getattr(module, "AGENT_TOOL_DOMAIN", None),
            "requires_workspace": getattr(module, "AGENT_REQUIRES_WORKSPACE", False),
            "execution_context": getattr(module, "AGENT_EXECUTION_CONTEXT", "auto"),
            "min_role": getattr(module, "AGENT_MIN_ROLE", "user"),
            "model_profile": getattr(module, "AGENT_MODEL_PROFILE", None),
            "tool_names": getattr(module, "AGENT_TOOL_NAMES", []),
        }

        self._agents[agent_id] = definition
        logger.debug("loaded agent: %s from %s", agent_id, py_file.name)

    def _create_default_general_agent(self) -> None:
        """Create a default general agent if none loaded."""
        self._agents["general"] = {
            "id": "general",
            "name": "General",
            "icon": "🧠",
            "description": "General purpose assistant",
            "system_prompt": "You are a helpful AI assistant.",
            "tool_domain": None,
            "tool_names": [],
            "requires_workspace": False,
            "execution_context": "auto",
            "min_role": "user",
            "model_profile": None,
        }

    def _apply_tool_mapping(self, all_tool_names: list[str]) -> None:
        """Apply AGENT_TOOL_MAP to all loaded agents."""
        for agent_id, agent_def in self._agents.items():
            tool_names = agent_def.get("tool_names", [])
            if not tool_names:
                mapped_tools = _get_tools_for_agent(agent_id, all_tool_names)
                agent_def["tool_names"] = mapped_tools
                logger.debug("agent %s: %d tools from mapping", agent_id, len(mapped_tools))

    def ensure_loaded(self) -> None:
        """Ensure agents are loaded (thread-safe, lazy loading)."""
        if self._loaded:
            return
        with self._lock:
            if not self._loaded:
                self._load_agents()
                self._loaded = True

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Get agent definition by ID."""
        self.ensure_loaded()
        agent = self._agents.get(agent_id)
        if agent:
            agent = dict(agent)
            tool_names = agent.get("tool_names", [])
            if not tool_names:
                all_tools = self._get_all_tool_names()
                logger.info("agent %s: found %d tools in registry: %s", agent_id, len(all_tools), all_tools[:20])
                mapped_tools = _get_tools_for_agent(agent_id, all_tools)
                agent["tool_names"] = mapped_tools
                logger.info("agent %s: mapped %d tools: %s", agent_id, len(mapped_tools), mapped_tools)
        return agent

    def _get_all_tool_names(self) -> list[str]:
        """Get all available tool names from the tool registry."""
        try:
            from apps.backend.domain.plugin_system.registry import get_registry
            reg = get_registry()
            tool_names = []
            for spec in reg.chat_tool_specs:
                fn = spec.get("function", {})
                n = fn.get("name")
                if n:
                    tool_names.append(n)
            return tool_names
        except Exception as e:
            logger.warning("could not load tool registry for agent mapping: %s", e)
            return []

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents."""
        self.ensure_loaded()
        return list(self._agents.values())

    def agent_ids(self) -> list[str]:
        """List all agent IDs."""
        self.ensure_loaded()
        return list(self._agents.keys())

    def to_list_dict(self) -> list[dict[str, Any]]:
        """Return list of agent definitions as dicts (for API)."""
        self.ensure_loaded()
        return list(self._agents.values())


_agent_registry: AgentRegistry | None = None
_registry_lock = threading.Lock()


def get_agent_registry() -> AgentRegistry:
    """Get the global agent registry instance."""
    global _agent_registry
    if _agent_registry is None:
        with _registry_lock:
            if _agent_registry is None:
                _agent_registry = AgentRegistry()
    return _agent_registry