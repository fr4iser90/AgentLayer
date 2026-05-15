"""Agent Registry - dynamically loads agent plugins and resolves tool allowlists from each plugin."""

from __future__ import annotations

import fnmatch
import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import Any

from apps.backend.core.config import PLUGINS_DIR

logger = logging.getLogger(__name__)

DEFAULT_AGENT_PLUGINS_DIR = PLUGINS_DIR / "agents"

# Fallback when no ``general`` plugin file is present (keep aligned with ``plugins/agents/general.py``).
_DEFAULT_GENERAL_TOOL_PATTERNS: tuple[str, ...] = (
    "coding.*",
    "fs.*",
    "list_tool_categories",
    "list_tools_in_category",
    "list_available_tools",
    "get_tool_help",
    "memory.*",
    "rag.*",
    "kb.*",
    "project.*",
    "search_web",
    "deep_search",
    "github.*",
    "openweather.*",
    "inpainting_realvision",
    "shopping.*",
    "pets.*",
    "ideas.*",
    "calendar.*",
    "gmail.*",
    "feeds.*",
    "todo.*",
    "get_current_time",
    "friends.*",
    "fishing.*",
    "hunting.*",
    "survival.*",
    "secrets.*",
    "register_secrets",
    "outdoor_environment_snapshot",
    "echo_text",
    "run_iterative_html_build",
    "schedule_job.*",
)


def _match_tool(tool_name: str, patterns: list[str]) -> bool:
    """True if ``tool_name`` matches any entry in ``patterns`` (exact, ``prefix.*``, or shell-style globs)."""
    for pattern in patterns:
        if pattern == tool_name:
            return True
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if tool_name.startswith(prefix):
                return True
        elif "*" in pattern or "?" in pattern or "[" in pattern:
            if fnmatch.fnmatchcase(tool_name, pattern):
                return True
    return False


def _tools_for_patterns(patterns: list[str], all_tool_names: list[str]) -> list[str]:
    """Resolve concrete tool names from pattern strings against the live tool registry."""
    if not patterns:
        return []
    matched: list[str] = []
    for tool_name in all_tool_names:
        if _match_tool(tool_name, patterns):
            matched.append(tool_name)
    return matched


def _tools_for_domains(
    domains: list[str],
    all_tool_names: list[str],
    *,
    include_introspection: bool,
) -> list[str]:
    """Tool names whose package ``domain`` is listed or ``shared`` (same idea as ``filter_merged_tools_by_domain``)."""
    allow = {d.strip().lower() for d in domains if str(d).strip()} | {"shared"}
    if not allow:
        return []
    from apps.backend.domain.plugin_system.registry import get_registry
    from apps.backend.domain.plugin_system.tool_routing import TOOL_INTROSPECTION

    intro = set(TOOL_INTROSPECTION) if include_introspection else set()
    reg = get_registry()
    out: list[str] = []
    for n in all_tool_names:
        if n in intro:
            out.append(n)
            continue
        meta = reg.meta_entry_for_tool_name(n)
        if not meta:
            continue
        dom = (meta.get("domain") or "").strip().lower()
        if dom in allow:
            out.append(n)
    return out


def _tools_for_capabilities_any(capabilities: list[str], all_tool_names: list[str]) -> list[str]:
    """Union of tools implementing any of the given capability strings (case-insensitive)."""
    cap_set = {c.strip().lower() for c in capabilities if str(c).strip()}
    if not cap_set:
        return []
    from apps.backend.domain.plugin_system.registry import get_registry

    reg = get_registry()
    idx = reg.capability_index
    matched: set[str] = set()
    for c in cap_set:
        for row in idx.get(c, []) or []:
            tn = row.get("tool_name")
            if isinstance(tn, str) and tn.strip():
                matched.add(tn.strip())
    allset = frozenset(all_tool_names)
    return sorted(n for n in matched if n in allset)


class AgentRegistry:
    """Registry that loads agent plugins and resolves tool allowlists per plugin."""

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

        explicit_raw = getattr(module, "AGENT_TOOL_NAMES", None)
        if isinstance(explicit_raw, (list, tuple)) and len(explicit_raw) > 0:
            tool_names = [str(x).strip() for x in explicit_raw if str(x).strip()]
            tool_patterns: list[str] = []
            tool_domains: list[str] = []
            tool_capability_any: list[str] = []
            tool_include_introspection = False
        else:
            tool_names = []
            p_attr = getattr(module, "AGENT_TOOL_PATTERNS", None)
            tool_patterns = list(p_attr) if isinstance(p_attr, (list, tuple)) else []
            d_attr = getattr(module, "AGENT_TOOL_DOMAINS", None)
            tool_domains = [str(x).strip().lower() for x in (d_attr or ()) if str(x).strip()]
            c_attr = getattr(module, "AGENT_TOOL_CAPABILITY_ANY", None)
            tool_capability_any = [str(x).strip() for x in (c_attr or ()) if str(x).strip()]
            tool_include_introspection = bool(getattr(module, "AGENT_TOOL_INCLUDE_INTROSPECTION", False))
            if not tool_patterns and not tool_domains and not tool_capability_any:
                logger.warning(
                    "agent %s (%s): set AGENT_TOOL_DOMAINS, AGENT_TOOL_CAPABILITY_ANY, and/or "
                    "AGENT_TOOL_PATTERNS (or non-empty AGENT_TOOL_NAMES) — no tools until configured",
                    agent_id,
                    py_file.name,
                )

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
            # Optional chat-loop behaviour (see ``docs/features/agent-registry-and-allowlists.md``).
            "strict_workspace": bool(getattr(module, "AGENT_STRICT_WORKSPACE", False)),
            "coding_tools_permission_ask": bool(getattr(module, "AGENT_CODING_TOOLS_PERMISSION_ASK", False)),
            "dedupe_identical_tool_calls": bool(getattr(module, "AGENT_DEDUPE_IDENTICAL_TOOL_CALLS", False)),
            "tool_discipline_preset": (
                str(getattr(module, "AGENT_TOOL_DISCIPLINE_PRESET", "") or "").strip().lower() or None
            ),
            "tool_patterns": tool_patterns,
            "tool_domains": tool_domains,
            "tool_capability_any": tool_capability_any,
            "tool_include_introspection": tool_include_introspection,
            "tool_names": tool_names,
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
            "tool_patterns": list(_DEFAULT_GENERAL_TOOL_PATTERNS),
            "tool_domains": [],
            "tool_capability_any": [],
            "tool_include_introspection": False,
            "tool_names": [],
            "requires_workspace": False,
            "execution_context": "auto",
            "min_role": "user",
            "model_profile": None,
            "strict_workspace": False,
            "coding_tools_permission_ask": False,
            "dedupe_identical_tool_calls": False,
            "tool_discipline_preset": None,
        }

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
            patterns = agent.get("tool_patterns") or []
            domains = agent.get("tool_domains") or []
            caps = agent.get("tool_capability_any") or []
            include_intro = bool(agent.get("tool_include_introspection", False))
            if not tool_names and (patterns or domains or caps):
                all_tools = self._get_all_tool_names()
                logger.info("agent %s: found %d tools in registry: %s", agent_id, len(all_tools), all_tools[:20])
                merged: set[str] = set()
                if patterns:
                    merged.update(_tools_for_patterns(patterns, all_tools))
                if domains:
                    merged.update(_tools_for_domains(domains, all_tools, include_introspection=include_intro))
                if caps:
                    merged.update(_tools_for_capabilities_any(caps, all_tools))
                mapped_tools = sorted(merged)
                agent["tool_names"] = mapped_tools
                logger.info("agent %s: mapped %d tools: %s", agent_id, len(mapped_tools), mapped_tools[:30])
        return agent

    def _get_all_tool_names(self) -> list[str]:
        """Get all available tool names from the tool registry."""
        try:
            from apps.backend.domain.plugin_system.registry import get_registry

            reg = get_registry()
            tool_names: list[str] = []
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
