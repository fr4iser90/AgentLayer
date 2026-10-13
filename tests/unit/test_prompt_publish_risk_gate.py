"""The LLM publish gate on agent prompt versions.

Decisions pinned here: the assessment runs at publish, a ``high`` verdict is a
hard block that only a site admin may pass (with a recorded reason), and an
unavailable assessment refuses the publish rather than waving it through.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from apps.backend.api.agents.controllers import agents_admin_api as api
from apps.backend.domain.access.capabilities import AdminScope
from apps.backend.domain.agent_runtime import prompt_risk as pr

_ACTOR = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_OWN_TENANT = 4
_OTHER_TENANT = 9
_VERSION = uuid.uuid4()


def _delegated() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=False, tenant_ids=frozenset({_OWN_TENANT}))


def _site() -> AdminScope:
    return AdminScope(actor_id=_ACTOR, site_wide=True, tenant_ids=frozenset())


def _reply(level, reasons=None, *, fenced=False):
    import json

    body = json.dumps({"level": level, "reasons": reasons or []})
    content = f"```json\n{body}\n```" if fenced else body
    return {"choices": [{"message": {"content": content}}]}, False


# --- domain: parsing and fail-closed behaviour ---


def test_parses_plain_json_verdict() -> None:
    risk = pr.assess_prompt_risk("be helpful", llm_call=lambda **kw: _reply("low", ["benign"]))
    assert risk.level == "low"
    assert risk.reasons == ("benign",)
    assert risk.blocking is False


def test_parses_fenced_json_verdict() -> None:
    risk = pr.assess_prompt_risk("x", llm_call=lambda **kw: _reply("high", ["exfil"], fenced=True))
    assert risk.level == "high"
    assert risk.blocking is True


def test_unusable_level_is_not_silently_treated_as_low() -> None:
    with pytest.raises(pr.PromptRiskUnavailable, match="unusable level"):
        pr.assess_prompt_risk("x", llm_call=lambda **kw: _reply("critical"))


def test_empty_content_fails_closed() -> None:
    with pytest.raises(pr.PromptRiskUnavailable, match="empty content"):
        pr.assess_prompt_risk(
            "x", llm_call=lambda **kw: ({"choices": [{"message": {"content": ""}}]}, False)
        )


def test_non_json_fails_closed() -> None:
    with pytest.raises(pr.PromptRiskUnavailable, match="did not return JSON"):
        pr.assess_prompt_risk(
            "x", llm_call=lambda **kw: ({"choices": [{"message": {"content": "looks fine to me"}}]}, False)
        )


def test_provider_exception_fails_closed_not_swallowed() -> None:
    def boom(**_kw):
        raise RuntimeError("provider unreachable")

    with pytest.raises(pr.PromptRiskUnavailable, match="provider call failed"):
        pr.assess_prompt_risk("x", llm_call=boom)


def test_empty_prompt_is_refused_before_the_llm() -> None:
    called: list = []
    with pytest.raises(pr.PromptRiskUnavailable, match="empty"):
        pr.assess_prompt_risk("   ", llm_call=lambda **kw: called.append(1) or _reply("low"))
    assert called == []


def test_domain_refuses_to_assess_without_an_injected_provider() -> None:
    """The domain must not resolve a client from infrastructure itself.

    Without this, a caller that forgot to wire ``llm_call`` would silently get
    some default behaviour instead of a refusal, and the gate could read as
    "assessed" while nothing was ever reached.
    """
    with pytest.raises(pr.PromptRiskUnavailable, match="no llm_call supplied"):
        pr.assess_prompt_risk("do the thing")


def test_gate_is_on_by_default(monkeypatch) -> None:
    monkeypatch.delenv(pr.GATE_ENABLED_ENV, raising=False)
    assert pr.gate_enabled() is True


def test_gate_kill_switch_turns_it_off(monkeypatch) -> None:
    monkeypatch.setenv(pr.GATE_ENABLED_ENV, "0")
    assert pr.gate_enabled() is False


def test_assessment_uses_a_short_timeout_not_the_120s_default() -> None:
    seen: dict = {}

    def spy(**kw):
        seen.update(kw)
        return _reply("low")

    pr.assess_prompt_risk("x", llm_call=spy)
    assert seen["timeout"] == pr.ASSESS_TIMEOUT_SEC
    assert pr.ASSESS_TIMEOUT_SEC < 60


# --- handler: the gate as an authorization decision ---


def _handler_patches(scope, *, verdict=None, gate=True, unavailable=False, published=None):
    def assess(*_a, **_kw):
        if unavailable:
            raise pr.PromptRiskUnavailable("provider down")
        return verdict

    published = published if published is not None else (lambda **kw: {"id": str(_VERSION)})
    db = MagicMock()
    db.user_tenant_id = MagicMock(return_value=_OWN_TENANT)
    return {
        "require_admin_scope": AsyncMock(return_value=scope),
        "db": db,
        "get_agent_prompt_version": lambda **kw: {"prompt_text": "do the thing"},
        "gate_enabled": lambda: gate,
        "assess_agent_prompt_risk": assess,
        "publish_agent_prompt_version": published,
    }


def _publish(scope, override_reason=None, **overrides):
    captured: dict = {}

    def publish(**kw):
        captured.update(kw)
        return {"id": str(_VERSION)}

    overrides.setdefault("published", publish)
    mocks = _handler_patches(scope, **overrides)
    with ExitStackMocks(mocks):
        out = asyncio.run(
            api.admin_publish_agent_prompt_version(
                MagicMock(), "todo_agent", _VERSION, tenant_id=None, override_reason=override_reason
            )
        )
    return out, captured


class ExitStackMocks:
    def __init__(self, mocks: dict) -> None:
        from contextlib import ExitStack

        self._stack = ExitStack()
        for name, value in mocks.items():
            self._stack.enter_context(patch.object(api, name, new=value))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)


def test_low_verdict_publishes_and_records_the_level() -> None:
    out, cap = _publish(_delegated(), verdict=pr.PromptRisk("low", ("benign",)))
    assert out["ok"] is True
    assert cap["risk_level"] == "low"
    assert cap["risk_reasons"] == ["benign"]
    assert cap["override_by"] is None


def test_high_verdict_blocks_a_delegated_admin() -> None:
    with pytest.raises(HTTPException) as exc:
        _publish(
            _delegated(),
            override_reason="because",
            verdict=pr.PromptRisk("high", ("exfiltrates secrets",)),
        )
    assert exc.value.status_code == 403


def test_high_verdict_site_admin_needs_a_reason() -> None:
    with pytest.raises(HTTPException) as exc:
        _publish(_site(), override_reason=None, verdict=pr.PromptRisk("high", ("exfil",)))
    assert exc.value.status_code == 400


def test_high_verdict_whitespace_reason_is_not_a_reason() -> None:
    with pytest.raises(HTTPException) as exc:
        _publish(_site(), override_reason="   ", verdict=pr.PromptRisk("high", ("exfil",)))
    assert exc.value.status_code == 400


def test_high_verdict_site_admin_override_records_who() -> None:
    out, cap = _publish(
        _site(),
        override_reason="reviewed with security, scoped to sandbox",
        verdict=pr.PromptRisk("high", ("exfil",)),
    )
    assert out["ok"] is True
    assert cap["risk_level"] == "high"
    assert cap["override_by"] == _ACTOR
    assert "security" in cap["override_reason"]


def test_unavailable_assessment_refuses_publish_with_503() -> None:
    published: list = []
    with pytest.raises(HTTPException) as exc:
        _publish(
            _site(),
            unavailable=True,
            published=lambda **kw: published.append(kw) or {},
        )
    assert exc.value.status_code == 503
    assert published == []


def test_kill_switch_publishes_unassessed_without_calling_the_llm() -> None:
    called: list = []
    out, _cap = _publish(
        _delegated(),
        gate=False,
        published=lambda **kw: called.append(kw) or {"id": "x"},
    )
    assert out["ok"] is True
    assert called[0]["risk_level"] == "unassessed"


def test_kill_switch_never_reaches_the_assessment() -> None:
    """A gate that is off must not spend a provider call on the way out."""
    assess = MagicMock(side_effect=AssertionError("assessed while gate was off"))
    mocks = _handler_patches(_delegated(), verdict=pr.PromptRisk("low", ()), gate=False)
    mocks["assess_agent_prompt_risk"] = assess
    with ExitStackMocks(mocks):
        out = asyncio.run(
            api.admin_publish_agent_prompt_version(
                MagicMock(), "todo_agent", _VERSION, tenant_id=None, override_reason=None
            )
        )
    assert out["ok"] is True
    assess.assert_not_called()


def test_missing_draft_is_404_before_the_gate_runs() -> None:
    assess = MagicMock(return_value=pr.PromptRisk("low", ()))
    mocks = _handler_patches(_delegated(), verdict=pr.PromptRisk("low", ()))
    mocks["get_agent_prompt_version"] = lambda **kw: None
    mocks["assess_agent_prompt_risk"] = assess
    with ExitStackMocks(mocks):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                api.admin_publish_agent_prompt_version(
                    MagicMock(), "todo_agent", _VERSION, tenant_id=None, override_reason=None
                )
            )
    assert exc.value.status_code == 404
    assess.assert_not_called()


# --- wiring: the application layer supplies the provider ---


def test_application_wrapper_supplies_the_catalog_client() -> None:
    """The gate only works if the application layer actually wires a provider.

    A missing wire would fail every publish with "no llm_call supplied". That
    is fail-closed, so nothing would leak, but the cause would be invisible —
    this pins the wiring itself rather than only the refusal it protects.
    """
    from apps.backend.application.agent_runtime.use_cases import (
        agent_governance_services as svc,
    )

    seen: dict = {}

    def fake_call(**kw):
        seen.update(kw)
        return _reply("medium", ["reaches into shells"])

    with patch(
        "apps.backend.infrastructure.agent_runtime.catalog_llm_client"
        ".post_catalog_chat_completions",
        new=fake_call,
    ):
        risk = svc.assess_agent_prompt_risk("do the thing", agent_id="todo_agent")

    assert risk.level == "medium"
    assert seen["timeout"] == pr.ASSESS_TIMEOUT_SEC
    assert "todo_agent" in seen["messages"][1]["content"]
