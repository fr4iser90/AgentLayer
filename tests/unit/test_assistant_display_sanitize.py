"""Tests for dashboard assistant display sanitization and tool recovery."""

from __future__ import annotations

import json

from apps.backend.domain.agent_runtime.assistant_display import (
    sanitize_assistant_display_text,
    synthetic_dashboard_tool_calls_from_message,
)


def test_sanitize_strips_tool_json_and_simulation_tail():
    raw = (
        "Hier sind Optionen.\n\n"
        '{"name": "propose_layouts", "arguments": {"proposals": [{"title": "A"}]}}\n\n'
        "**Warte auf Benutzereingabe.**\n**Benutzer:** Variante 1"
    )
    out = sanitize_assistant_display_text(raw)
    assert "propose_layouts" not in out
    assert "Warte auf Benutzereingabe" not in out
    assert "Benutzer" not in out
    assert "Hier sind Optionen" in out


def test_sanitize_strips_thought_block():
    raw = "[Thought]\nplanning...\n\nSichtbare Antwort."
    out = sanitize_assistant_display_text(raw)
    assert "planning" not in out
    assert "Sichtbare Antwort" in out


def test_synthetic_propose_layouts_from_message():
    proposals = [
        {
            "title": "A",
            "summary": "s",
            "ui_layout": {"version": 1, "blocks": []},
        }
    ]
    msg = {
        "role": "assistant",
        "content": json.dumps(
            {
                "name": "propose_layouts",
                "arguments": {
                    "dashboard_id": "x",
                    "proposals": proposals,
                },
            }
        ),
    }
    tc = synthetic_dashboard_tool_calls_from_message(
        msg,
        allowed_tool_names={"propose_layouts", "dashboard.read"},
    )
    assert tc is not None
    assert tc[0]["function"]["name"] == "propose_layouts"
    args = json.loads(tc[0]["function"]["arguments"])
    assert len(args["proposals"]) == 1
