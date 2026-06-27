"""Reviewer tools must not expose config apply or benchmark start."""

from __future__ import annotations


def test_reviewer_handlers_are_read_only_or_review():
    from plugins.tools.platform.reviewer import audit as reviewer_tools

    forbidden = {
        "agent_config_apply",
        "settings_patch",
        "benchmark_run_start",
        "benchmark_experiment_run",
    }
    assert forbidden.isdisjoint(set(reviewer_tools.HANDLERS.keys()))
    assert "review_submit" in reviewer_tools.HANDLERS
    assert "review_recommend_patches" in reviewer_tools.HANDLERS


def test_delegate_disabled_returns_error(monkeypatch):
    from plugins.tools.platform.agents import delegate as delegate_mod

    monkeypatch.setattr(
        "apps.backend.infrastructure.settings.operator_settings.delegate_enabled",
        lambda: False,
    )
    out = delegate_mod.delegate({"run_subagent": True, "agent_id": "coding", "prompt": "hi"}, {})
    payload = __import__("json").loads(out)
    assert payload.get("ok") is False
    assert "disabled" in str(payload.get("error") or "").lower()
