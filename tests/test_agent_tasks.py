"""Agent OS tasks, artifacts, and delegate prompt enrichment."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from apps.backend.domain.agent_task_prompt import (
    build_artifact_context_block,
    enrich_delegate_prompt,
    format_requirements_block,
)
from plugins.tools.capabilities.platform.agent_delegate import agent_delegate


def test_format_requirements_block() -> None:
    out = format_requirements_block(["auth", "tests"])
    assert "auth" in out
    assert "tests" in out


def test_enrich_delegate_prompt_empty() -> None:
    assert enrich_delegate_prompt(tenant_id=1, base_prompt="do thing") == "do thing"


def test_build_artifact_context_block_missing() -> None:
    with patch(
        "apps.backend.domain.agent_task_prompt.agent_artifacts_store.get_artifact",
        return_value=None,
    ):
        block = build_artifact_context_block(
            tenant_id=1, artifact_refs=[str(uuid.uuid4())]
        )
    assert "not found" in block


def test_delegate_requires_run_subagent() -> None:
    out = agent_delegate({"agent_id": "coding", "prompt": "x"}, context=None)
    data = json.loads(out)
    assert data.get("ok") is False


def test_delegate_passes_artifact_refs_to_subagent() -> None:
    aid = str(uuid.uuid4())
    with patch(
        "plugins.tools.capabilities.platform.agent_delegate.run_embedded_subagent_sync",
        return_value='{"ok": true}',
    ) as mock_run:
        agent_delegate(
            {
                "run_subagent": True,
                "agent_id": "coding_plan",
                "prompt": "explore",
                "description": "plan",
                "artifact_refs": [aid],
                "requirements": ["read-only"],
            },
            context={"parent_effective_model": "m", "parent_model_catalog_owned_by": "ollama"},
        )
    mock_run.assert_called_once()
    kw = mock_run.call_args.kwargs
    assert kw.get("artifact_refs") == [aid]
    assert kw.get("requirements") == ["read-only"]
