"""Memory graph prompt injection (graph_render_for_identity)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from apps.backend.infrastructure.memory import memory_service as memory_api


def test_graph_render_for_identity_uses_max_hops_from_settings() -> None:
    row = {
        "id": 1,
        "kind": "event",
        "label": "homelab",
        "summary": "Jetson nodes",
        "importance": 1.0,
        "confidence": 1.0,
        "stability": "normal",
        "priority": 0.0,
        "updated_at": datetime.now(UTC),
    }
    with (
        patch.object(memory_api, "_memory_graph_enabled", return_value=True),
        patch.object(memory_api, "_require_identity"),
        patch.object(
            memory_api.operator_settings,
            "memory_graph_prompt_settings",
            return_value={
                "enabled": True,
                "max_hops": 3,
                "min_score": 0.03,
                "max_bullets": 14,
                "max_prompt_chars": 3500,
                "log_activations": False,
            },
        ),
        patch.object(memory_api, "embed_one", return_value=[0.1] * 768),
        patch.object(memory_api.db, "memory_graph_activate", return_value=[row]) as activate,
        patch.object(memory_api, "_maybe_log_graph_activation"),
    ):
        out = memory_api.graph_render_for_identity(
            dashboard_id=uuid.uuid4(),
            user_query="tell me about my homelab",
        )
    assert "[User memory — graph]" in out
    assert "homelab" in out
    assert activate.call_args.kwargs["max_hops"] == 3


def test_graph_render_disabled_returns_empty() -> None:
    with patch.object(memory_api, "_memory_graph_enabled", return_value=False):
        assert memory_api.graph_render_for_identity(dashboard_id=None, user_query="x") == ""
