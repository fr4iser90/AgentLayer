"""Load agent personas from ``plugins/agents/<id>/agent.yaml`` + ``system_prompt.md``."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from apps.backend.core.config import PLUGINS_DIR

logger = logging.getLogger(__name__)


def _as_str_list(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw.strip()] if raw.strip() else []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def _read_system_prompt(agent_dir: Path, data: dict[str, Any]) -> str:
    inline = data.get("system_prompt")
    if isinstance(inline, str) and inline.strip():
        return inline
    prompt_file = str(data.get("system_prompt_file") or "system_prompt.md").strip()
    prompt_path = agent_dir / prompt_file
    if prompt_path.is_file():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning("agent %s: no system_prompt in yaml and missing %s", data.get("id"), prompt_path)
    return ""


def definition_from_yaml(agent_dir: Path, yaml_path: Path) -> dict[str, Any] | None:
    """Parse ``agent.yaml`` into a registry definition dict."""
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to parse %s: %s", yaml_path, e)
        return None
    if not isinstance(raw, dict):
        logger.warning("agent yaml must be a mapping: %s", yaml_path)
        return None

    data = dict(raw)
    agent_id = str(data.get("id") or agent_dir.name).strip()
    if not agent_id:
        logger.warning("agent yaml missing id: %s", yaml_path)
        return None

    tool_domains = [d.lower() for d in _as_str_list(data.get("tool_domains"))]
    pinned_tools = [str(x).strip() for x in _as_str_list(data.get("pinned_tools")) if str(x).strip()]
    prefer_full = [
        str(x).strip() for x in _as_str_list(data.get("tool_forward_prefer_full_schema")) if str(x).strip()
    ]
    tool_capability_any = _as_str_list(data.get("tool_capability_any"))
    preset_val = data.get("tool_discipline_preset")
    preset_norm = str(preset_val).strip().lower() if preset_val else None
    if preset_norm == "":
        preset_norm = None

    tool_domain = data.get("tool_domain")
    if tool_domain is not None:
        tool_domain = str(tool_domain).strip() or None

    try:
        rel_source = yaml_path.relative_to(PLUGINS_DIR.parent).as_posix()
    except ValueError:
        rel_source = yaml_path.as_posix()

    return {
        "id": agent_id,
        "name": str(data.get("name") or agent_id),
        "icon": str(data.get("icon") or "🤖"),
        "description": str(data.get("description") or ""),
        "system_prompt": _read_system_prompt(agent_dir, data),
        "tool_domain": tool_domain,
        "requires_workspace": bool(data.get("requires_workspace", False)),
        "schedulable": bool(data.get("schedulable", True)),
        "execution_context": str(data.get("execution_context") or "auto"),
        "min_role": str(data.get("min_role") or "user"),
        "model_profile": (
            str(data.get("model_profile")).strip() if data.get("model_profile") is not None else None
        ) or None,
        "strict_workspace": bool(data.get("strict_workspace", False)),
        "coding_tools_permission_ask": bool(data.get("coding_tools_permission_ask", False)),
        "tool_discipline_preset": preset_norm,
        "tool_domains": tool_domains,
        "pinned_tools": pinned_tools,
        "tool_forward_prefer_full_schema": prefer_full,
        "tool_capability_any": tool_capability_any,
        "tool_include_introspection": bool(data.get("tool_include_introspection", False)),
        "source_kind": "yaml",
        "source_path": rel_source,
    }


def discover_yaml_agents(plugins_dir: Path) -> list[tuple[Path, Path]]:
    """Return ``(agent_dir, agent.yaml)`` pairs under ``plugins_dir``."""
    found: list[tuple[Path, Path]] = []
    if not plugins_dir.is_dir():
        return found
    for child in sorted(plugins_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        yaml_path = child / "agent.yaml"
        if yaml_path.is_file():
            found.append((child, yaml_path))
    return found
