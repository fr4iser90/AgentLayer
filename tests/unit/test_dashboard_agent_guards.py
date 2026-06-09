"""Dashboard-agent layout guards (not tool-forward policy)."""

from __future__ import annotations

from apps.backend.domain.dashboard_agent_guards import (
    dashboard_layout_proposal_nudge_needed,
    is_propose_layouts_tool,
    layout_proposal_intent,
)


def test_layout_proposal_intent_german_variants():
    assert layout_proposal_intent("Zeig mir 3 Layout-Varianten")
    assert not layout_proposal_intent("wie viele projekte habe ich")


def test_dashboard_layout_proposal_nudge_needed():
    names = frozenset({"dashboard.read", "propose_layouts", "patch_layout"})
    assert dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=0,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=True,
        nudge_count=0,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="dashboard",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=2,
        forwarded_tool_names=names,
    )
    assert not dashboard_layout_proposal_nudge_needed(
        agent_id="coding",
        layout_proposal_required=True,
        propose_layouts_done=False,
        nudge_count=0,
        forwarded_tool_names=names,
    )


def test_is_propose_layouts_tool():
    assert is_propose_layouts_tool("propose_layouts")
    assert is_propose_layouts_tool("dashboard.propose_layouts")
    assert not is_propose_layouts_tool("patch_layout")
