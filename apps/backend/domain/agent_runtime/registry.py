"""Agent Registry - loads agent plugins and resolves tool allowlists (domains + capabilities only)."""

from __future__ import annotations

import importlib.util
import logging
import threading
from pathlib import Path
from typing import Any, Protocol

from apps.backend.domain.agent_runtime.plugin_loader import definition_from_yaml, discover_yaml_agents

logger = logging.getLogger(__name__)


class AgentRegistryDependencies(Protocol):
    def policies_map(self) -> dict[tuple[str, str], dict[str, Any]]: ...

    def merge_agent_definition(self, agent: dict[str, Any]) -> dict[str, Any]: ...

    def agent_plugin_dirs(self) -> list[Path]: ...

    def plugins_root(self) -> Path | None: ...


_deps: AgentRegistryDependencies | None = None


def register_agent_registry_dependencies(deps: AgentRegistryDependencies) -> None:
    global _deps
    _deps = deps


def policies_map() -> dict[tuple[str, str], dict[str, Any]]:
    return _deps.policies_map() if _deps is not None else {}


def merge_agent_definition(agent: dict[str, Any]) -> dict[str, Any]:
    return _deps.merge_agent_definition(agent) if _deps is not None else agent


def agent_plugin_dirs() -> list[Path]:
    return _deps.agent_plugin_dirs() if _deps is not None else []


def plugins_root() -> Path | None:
    return _deps.plugins_root() if _deps is not None else None


def _tools_for_domains(
    domains: list[str],
    all_tool_names: list[str],
    *,
    include_introspection: bool,
    include_shared: bool = False,
) -> list[str]:
    """Tool names whose package ``domain`` is listed; ``shared`` only when requested."""
    allow = {d.strip().lower() for d in domains if str(d).strip()}
    if include_shared:
        allow.add("shared")
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


def resolve_agent_tool_names(definition: dict[str, Any], all_tool_names: list[str] | None = None) -> list[str]:
    """Resolve ``tool_names`` for an agent definition dict (allowlist, domains + capabilities)."""
    if all_tool_names is None:
        all_tool_names = _get_all_tool_names_static()
    all_tools = frozenset(all_tool_names)
    allowlist = definition.get("tool_allowlist") or []
    if allowlist:
        return sorted(n for n in allowlist if n in all_tools)
    domains = definition.get("tool_domains") or []
    caps = definition.get("tool_capability_any") or []
    include_intro = bool(definition.get("tool_include_introspection", False))
    merged: set[str] = set()
    include_shared = bool(definition.get("tool_include_shared", False))
    if domains:
        merged.update(
            _tools_for_domains(
                domains,
                sorted(all_tools),
                include_introspection=include_intro,
                include_shared=include_shared,
            )
        )
    if caps:
        merged.update(_tools_for_capabilities_any(caps, sorted(all_tools)))
    return sorted(n for n in merged if n in all_tools)


def effective_tool_names_for_caller(
    agent_id: str,
    *,
    user_role: str | None,
    tenant_id: int,
) -> list[str]:
    """Agent allowlist intersected with operator tool policy for a role/tenant."""
    agent = get_agent_registry().get_agent(agent_id)
    if not agent:
        return []
    names = set(agent.get("tool_names") or [])
    if not names:
        return []
    try:
        from apps.backend.domain.plugin_system.registry import get_registry
        from apps.backend.domain.plugin_system.tool_policy import filter_chat_tool_specs

        reg = get_registry()
        specs = [s for s in reg.chat_tool_specs if (s.get("function") or {}).get("name") in names]
        filtered = filter_chat_tool_specs(specs, reg, policies_map(), user_role, tenant_id)
        return sorted(
            str((s.get("function") or {}).get("name"))
            for s in filtered
            if (s.get("function") or {}).get("name")
        )
    except Exception:
        logger.debug("effective_tool_names_for_caller skipped", exc_info=True)
        return sorted(names)


def _get_all_tool_names_static() -> list[str]:
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

            for _agent_dir, yaml_path in discover_yaml_agents(plugins_dir):
                try:
                    self._load_agent_from_yaml(yaml_path, seen_ids)
                except Exception as e:
                    logger.warning("failed to load agent from %s: %s", yaml_path, e)

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
        return list(agent_plugin_dirs())

    def _register_definition(self, definition: dict[str, Any], seen_ids: set[str], label: str) -> None:
        agent_id = definition["id"]
        if agent_id in seen_ids:
            logger.warning("duplicate agent_id %s in %s, skipping", agent_id, label)
            return
        seen_ids.add(agent_id)

        tool_domains = definition.get("tool_domains") or []
        tool_capability_any = definition.get("tool_capability_any") or []
        tool_allowlist = definition.get("tool_allowlist") or []
        if not tool_domains and not tool_capability_any and not tool_allowlist:
            logger.warning(
                "agent %s (%s): set tool_allowlist and/or tool_domains and/or tool_capability_any — no tools until configured",
                agent_id,
                label,
            )

        self._agents[agent_id] = definition
        logger.debug("loaded agent: %s from %s", agent_id, label)

    def _load_agent_from_yaml(self, yaml_path: Path, seen_ids: set[str]) -> None:
        definition = definition_from_yaml(yaml_path.parent, yaml_path, source_root=plugins_root())
        if not definition:
            return
        self._register_definition(definition, seen_ids, yaml_path.name)

    def _load_agent_from_file(self, py_file: Path, seen_ids: set[str]) -> None:
        """Load agent definition from a legacy Python module (``plugins/agents/*.py``)."""
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
            logger.debug("agent %s already loaded from yaml, skipping %s", agent_id, py_file.name)
            return

        d_attr = getattr(module, "AGENT_TOOL_DOMAINS", None)
        tool_domains = [str(x).strip().lower() for x in (d_attr or ()) if str(x).strip()]
        c_attr = getattr(module, "AGENT_TOOL_CAPABILITY_ANY", None)
        tool_capability_any = [str(x).strip() for x in (c_attr or ()) if str(x).strip()]
        tool_include_introspection = bool(getattr(module, "AGENT_TOOL_INCLUDE_INTROSPECTION", False))

        if getattr(module, "AGENT_TOOL_PATTERNS", None) or getattr(module, "AGENT_TOOL_NAMES", None):
            logger.warning(
                "agent %s (%s): AGENT_TOOL_PATTERNS / AGENT_TOOL_NAMES are deprecated — "
                "use tool_domains and/or tool_capability_any only",
                agent_id,
                py_file.name,
            )

        try:
            source_root = plugins_root()
            rel_source = py_file.relative_to(source_root).as_posix() if source_root else py_file.as_posix()
        except ValueError:
            rel_source = py_file.as_posix()
        definition = {
            "id": agent_id,
            "name": getattr(module, "AGENT_NAME", agent_id),
            "icon": getattr(module, "AGENT_ICON", "🤖"),
            "description": getattr(module, "AGENT_DESCRIPTION", ""),
            "system_prompt": getattr(module, "AGENT_SYSTEM_PROMPT", ""),
            "tool_domain": getattr(module, "AGENT_TOOL_DOMAIN", None),
            "requires_workspace": getattr(module, "AGENT_REQUIRES_WORKSPACE", False),
            "schedulable": bool(getattr(module, "AGENT_SCHEDULABLE", True)),
            "execution_context": getattr(module, "AGENT_EXECUTION_CONTEXT", "auto"),
            "min_role": getattr(module, "AGENT_MIN_ROLE", "user"),
            "model_profile": getattr(module, "AGENT_MODEL_PROFILE", None),
            "strict_workspace": bool(getattr(module, "AGENT_STRICT_WORKSPACE", False)),
            "coding_tools_permission_ask": bool(getattr(module, "AGENT_CODING_TOOLS_PERMISSION_ASK", False)),
            "tool_discipline_preset": (
                str(getattr(module, "AGENT_TOOL_DISCIPLINE_PRESET", "") or "").strip().lower() or None
            ),
            "tool_domains": tool_domains,
            "tool_capability_any": tool_capability_any,
            "tool_include_introspection": tool_include_introspection,
            "source_kind": "python",
            "source_path": rel_source,
        }

        self._register_definition(definition, seen_ids, py_file.name)

    def _create_default_general_agent(self) -> None:
        """Minimal stub when ``plugins/agents/general/`` is missing."""
        logger.error(
            "no general agent plugin loaded — add plugins/agents/general/agent.yaml with "
            "tool_domains and/or tool_capability_any"
        )
        self._agents["general"] = {
            "id": "general",
            "name": "General",
            "icon": "🧠",
            "description": "General purpose assistant (plugin missing — no tools until general is loaded)",
            "system_prompt": "You are a helpful AI assistant.",
            "tool_domain": None,
            "tool_domains": [],
            "tool_capability_any": [],
            "tool_include_introspection": False,
            "requires_workspace": False,
            "schedulable": True,
            "execution_context": "auto",
            "min_role": "user",
            "model_profile": None,
            "strict_workspace": False,
            "coding_tools_permission_ask": False,
            "tool_discipline_preset": None,
            "source_kind": "builtin",
            "source_path": None,
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
        """Get agent definition by ID with ``tool_names`` resolved against the live tool registry."""
        self.ensure_loaded()
        agent = self._agents.get(agent_id)
        if not agent:
            return None
        agent = dict(agent)
        agent = merge_agent_definition(agent)
        agent["tool_names"] = resolve_agent_tool_names(agent)
        return agent

    def _get_all_tool_names(self) -> list[str]:
        return _get_all_tool_names_static()

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
