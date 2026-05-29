"""Resolve per-workspace index-on-write policy and retrieve_context source defaults."""

from __future__ import annotations

from typing import Any

_VALID_INDEX_ON_WRITE = frozenset({"off", "debounced", "immediate"})
_DEFAULT_RETRIEVE_SOURCES = ("code_grep", "code_semantic", "docs")
_VALID_RETRIEVE_SOURCE_IDS = frozenset(
    {"code_grep", "code_semantic", "docs", "memory", "graph"}
)


def normalize_index_on_write(raw: Any) -> str | None:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if not v or v == "inherit":
        return None
    if v in _VALID_INDEX_ON_WRITE:
        return v
    return None


def operator_index_on_write_default() -> str:
    from apps.backend.infrastructure.operator_settings import fetch_operator_settings_row

    r = fetch_operator_settings_row()
    v = normalize_index_on_write(r.get("workspace_index_on_write_default"))
    if v:
        return v
    from apps.backend.core.config import config

    return config.AGENT_WORKSPACE_INDEX_ON_WRITE


def effective_index_on_write(workspace: dict[str, Any] | None) -> str:
    """Workspace override, else operator default, else env default."""
    if workspace:
        ws_val = normalize_index_on_write(workspace.get("index_on_write"))
        if ws_val:
            return ws_val
    return operator_index_on_write_default()


def graph_index_enabled_for_workspace(workspace: dict[str, Any] | None) -> bool:
    if not workspace:
        return True
    if workspace.get("graph_index_enabled") is False:
        return False
    return True


def parse_retrieve_context_sources(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(",", " ").split() if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        return None
    out = [p for p in parts if p in _VALID_RETRIEVE_SOURCE_IDS]
    return out or None


def default_retrieve_sources_for_agent(agent_id: str | None) -> list[str]:
    aid = (agent_id or "").strip().lower()
    if aid == "coding_plan":
        return list(_DEFAULT_RETRIEVE_SOURCES)
    return list(_DEFAULT_RETRIEVE_SOURCES)


def resolve_retrieve_context_sources(
    workspace: dict[str, Any] | None,
    *,
    agent_id: str | None = None,
    requested: Any = None,
) -> list[str]:
    """Explicit tool arg wins; else workspace JSON; else agent default."""
    explicit = parse_retrieve_context_sources(requested)
    if explicit is not None:
        return explicit
    if workspace:
        ws_sources = parse_retrieve_context_sources(workspace.get("retrieve_context_sources"))
        if ws_sources is not None:
            return ws_sources
    return default_retrieve_sources_for_agent(agent_id)
