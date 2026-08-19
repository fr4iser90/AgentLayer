"""Tests for agents catalog tool and builder."""

from __future__ import annotations

import json

from apps.backend.domain.agent_runtime.catalog import build_agents_catalog


def test_build_agents_catalog_includes_general() -> None:
    out = build_agents_catalog(user_role="user", tenant_id=1)
    assert out["ok"] is True
    ids = {a["id"] for a in out["agents"]}
    assert "general" in ids
    general = next(a for a in out["agents"] if a["id"] == "general")
    assert general["invokable_by_caller"] is True
    assert general["delegatable"] is False
    assert "tool_names" not in general
    assert general["tool_domains"] == []
    assert general["tool_capability_any"] == []
    assert general["tool_names_count"] == 3
    assert "icon" not in general
    assert all("icon" not in a for a in out["agents"])


def test_delegatable_agents_include_tool_names_for_user() -> None:
    out = build_agents_catalog(user_role="user", tenant_id=1, delegatable_only=True)
    research = next(a for a in out["agents"] if a["id"] == "research")
    assert "tool_names" in research
    assert "web_search.search" in research["tool_names"]


def test_delegatable_only_filters() -> None:
    out = build_agents_catalog(user_role="user", tenant_id=1, delegatable_only=True)
    ids = {a["id"] for a in out["agents"]}
    assert "general" not in ids
    assert "research" in ids
    assert "coding" not in ids


def test_admin_include_tool_names() -> None:
    out = build_agents_catalog(user_role="admin", tenant_id=1, include_tool_names=True)
    research = next(a for a in out["agents"] if a["id"] == "research")
    assert "tool_names" in research
    assert "web_search.search" in research.get("tool_names", [])


def test_catalog_tool_smoke() -> None:
    from plugins.tools.platform.agents.catalog import catalog

    raw = catalog({}, context={"user_role": "user"})
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["agent_count"] >= 1
