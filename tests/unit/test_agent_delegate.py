"""delegate tool and general delegate catalog."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

from apps.backend.domain.embedded_subagent import (
    admin_only_delegatable_agent_ids,
    build_delegate_agents_catalog_snippet,
    effective_delegatable_agent_ids,
    standard_delegatable_agent_ids,
)
from plugins.tools.platform.agents.delegate import delegate


def test_delegatable_agent_ids() -> None:
    assert "security_auditor" in standard_delegatable_agent_ids()
    assert "coding" in standard_delegatable_agent_ids()
    assert "creative" in standard_delegatable_agent_ids()
    assert "dashboard" in standard_delegatable_agent_ids()
    assert "math" in standard_delegatable_agent_ids()
    assert "research" in standard_delegatable_agent_ids()
    assert "communications" in standard_delegatable_agent_ids()
    assert "media" in standard_delegatable_agent_ids()
    assert "operator" in admin_only_delegatable_agent_ids()
    assert "operator" not in standard_delegatable_agent_ids()
    assert "general" not in standard_delegatable_agent_ids()


def test_effective_delegatable_includes_operator_for_admin() -> None:
    base = effective_delegatable_agent_ids(caller_is_admin=False)
    admin = effective_delegatable_agent_ids(caller_is_admin=True)
    assert "operator" not in base
    assert "operator" in admin


def test_list_agents_includes_operator_for_admin() -> None:
    uid = uuid.uuid4()
    ctx = {"user": type("U", (), {"id": uid})()}
    with patch(
        "plugins.tools.platform.agents.delegate.caller_is_admin",
        return_value=True,
    ):
        out = delegate({"list_agents": True}, context=ctx)
    data = json.loads(out)
    assert data.get("ok") is True
    assert "operator" in data.get("agent_ids", [])


def test_list_agents_excludes_operator_for_non_admin() -> None:
    out = delegate({"list_agents": True}, context=None)
    data = json.loads(out)
    assert data.get("ok") is True
    assert "operator" not in data.get("agent_ids", [])


def test_catalog_snippet_mentions_operator_for_admin() -> None:
    snip = build_delegate_agents_catalog_snippet(caller_is_admin=True)
    assert "operator" in snip
    assert "media library" in snip.lower() or "platform settings" in snip.lower()


def test_catalog_snippet_lists_specialists() -> None:
    snip = build_delegate_agents_catalog_snippet()
    assert "delegate" in snip
    assert "security_auditor" in snip
    assert "coding" in snip


def test_list_agents_mode() -> None:
    out = delegate({"list_agents": True}, context=None)
    data = json.loads(out)
    assert data.get("ok") is True
    assert "security_auditor" in data.get("agent_ids", [])


def test_delegate_requires_parent_model_from_ui() -> None:
    out = delegate(
        {
            "run_subagent": True,
            "agent_id": "coding",
            "prompt": "do work",
            "description": "build",
        },
        context={"agent_run_id": "p1"},
    )
    data = json.loads(out)
    assert data.get("ok") is False
    assert "catalog" in (data.get("error") or "").lower() or "UI" in (data.get("error") or "")


def test_delegate_requires_run_subagent() -> None:
    out = delegate(
        {"agent_id": "security_auditor", "prompt": "scan", "description": "ssc"},
        context=None,
    )
    data = json.loads(out)
    assert data.get("ok") is False


def test_delegate_invokes_security_auditor() -> None:
    uid = uuid.uuid4()
    ctx = {
        "workspace": {"id": str(uuid.uuid4()), "path": "/tmp/ws"},
        "user": type("U", (), {"id": uid})(),
        "agent_run_id": "parent-1",
        "parent_effective_model": "__mock_ui_model__",
        "parent_model_catalog_owned_by": "__mock_ui_provider__",
    }
    bodies: list[dict] = []

    async def fake_cc(body: dict, **kwargs: object) -> dict:
        bodies.append(dict(body))
        return {"choices": [{"message": {"content": "Scan report."}, "finish_reason": "stop"}]}

    art_id = uuid.uuid4()
    with patch("apps.backend.domain.agent.chat_completion", new=AsyncMock(side_effect=fake_cc)):
        with patch("apps.backend.domain.identity.get_identity", return_value=(1, uid)):
            with patch(
                "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
                return_value={"id": art_id},
            ):
                with patch(
                    "apps.backend.infrastructure.agent_runs_store.insert_run_start_resilient",
                    return_value=({"id": uuid.uuid4()}, []),
                ):
                    with patch(
                        "apps.backend.infrastructure.agent_runs_store.finish_run",
                        return_value=True,
                    ):
                        out = delegate(
                            {
                                "run_subagent": True,
                                "agent_id": "security_auditor",
                                "prompt": "Run SSC scan and summarize findings",
                                "description": "SSC scan",
                            },
                            context=ctx,
                        )

    data = json.loads(out)
    assert data.get("ok") is True, data
    assert data.get("artifact_id") == str(art_id)
    assert data.get("agent_id") == "security_auditor"
    assert len(bodies) == 1
    assert bodies[0].get("agent_id") == "security_auditor"
    assert bodies[0].get("model") == "__mock_ui_model__"
    assert bodies[0].get("agent_model_catalog_owned_by") == "__mock_ui_provider__"
