"""Unit tests for per-model harness override matching and effective resolution."""

from __future__ import annotations

from unittest.mock import patch

from apps.backend.infrastructure.agent_config_model_resolve import match_model_override


def test_match_model_override_exact_before_provider():
    rows = [
        {"id": "1", "catalog_owned_by": "provider_2", "model": "", "knobs_json": {"a": 1}},
        {"id": "2", "catalog_owned_by": "provider_2", "model": "llama-3", "knobs_json": {"a": 2}},
    ]
    matched, source = match_model_override(rows, catalog_owned_by="provider_2", model="llama-3")
    assert matched is not None
    assert matched["id"] == "2"
    assert source == "model_db_override"


def test_match_model_override_provider_fallback():
    rows = [
        {"id": "1", "catalog_owned_by": "provider_2", "model": "", "knobs_json": {"a": 1}},
    ]
    matched, source = match_model_override(rows, catalog_owned_by="provider_2", model="other-model")
    assert matched is not None
    assert matched["id"] == "1"
    assert source == "provider_db_override"


def test_effective_value_model_override_priority():
    from apps.backend.infrastructure import agent_config_effective

    rows = [
        {
            "id": "1",
            "catalog_owned_by": "provider_2",
            "model": "m1",
            "knobs_json": {"agent.max_tool_rounds": 7},
        }
    ]
    with patch("apps.backend.infrastructure.agent_config_effective.db.pool_ready", return_value=True):
        with patch.object(agent_config_effective, "_cached_model_override_rows", return_value=rows):
            with patch.object(agent_config_effective, "_cached_overrides", return_value={"agent.max_tool_rounds": 20}):
                val, src = agent_config_effective.effective_value(
                    "agent.max_tool_rounds",
                    tenant_id=1,
                    catalog_owned_by="provider_2",
                    model="m1",
                )
    assert val == 7
    assert src == "model_db_override"
