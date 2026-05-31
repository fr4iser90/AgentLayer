"""Generic delegate enforcement (Option B orchestration)."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.domain.delegate_enforcement import (
    coding_delegate_tool_blocked,
    extract_handoff_artifact_ids,
    general_orchestrator_tool_blocked,
    load_delegate_allowed_paths,
    paths_from_artifact_content,
    subagent_reject_reason,
)


def test_paths_from_artifact_content_generic() -> None:
    content = {
        "high_paths": ["apps/foo.py"],
        "findings": [{"path": "plugins/bar.py", "severity": "HIGH"}],
    }
    paths = paths_from_artifact_content(content)
    assert "apps/foo.py" in paths
    assert "plugins/bar.py" in paths


def test_fix_from_artifact_blocks_out_of_scope_edit() -> None:
    ctx = {
        "agent_delegate_mode": "fix_from_artifact",
        "agent_delegate_allowed_paths": ["plugins/foo.py"],
    }
    msg = coding_delegate_tool_blocked(
        "edit",
        {"path": "apps/other.py", "old_string": "a", "new_string": "b"},
        ctx,
    )
    assert msg is not None
    assert "not in artifact scope" in msg


def test_fix_from_artifact_allows_scoped_edit() -> None:
    ctx = {
        "agent_delegate_mode": "fix_from_artifact",
        "agent_delegate_allowed_paths": ["plugins/foo.py"],
    }
    assert (
        coding_delegate_tool_blocked(
            "edit",
            {"path": "plugins/foo.py", "old_string": "a", "new_string": "b"},
            ctx,
        )
        is None
    )


def test_fix_from_artifact_blocks_wrong_branch_push() -> None:
    ctx = {
        "agent_delegate_mode": "fix_from_artifact",
        "agent_delegate_allowed_paths": ["plugins/foo.py"],
        "agent_delegate_required_branch": "security/fix-high-issues",
    }
    msg = coding_delegate_tool_blocked(
        "git_push",
        {"branch": "security/fix-other"},
        ctx,
    )
    assert msg is not None
    assert "required branch" in msg


def test_general_blocks_search_when_handoff_pending() -> None:
    ctx = {"orchestrator_pending_artifact_refs": ["abc-123"]}
    msg = general_orchestrator_tool_blocked("search", {"query": "x"}, ctx)
    assert msg is not None
    assert "delegate" in msg


def test_reject_plan_for_fix_from_artifact() -> None:
    msg = subagent_reject_reason(
        agent_id="coding_plan",
        requirements=["mode: fix_from_artifact"],
    )
    assert msg is not None
    assert "coding_plan is read-only" in msg


def test_handoff_artifact_ids_from_delegate_payload() -> None:
    raw = '{"ok": true, "handoff_artifact_ids": ["id-1", "id-2"]}'
    assert extract_handoff_artifact_ids(raw) == ["id-1", "id-2"]


def test_load_delegate_allowed_paths() -> None:
    aid = uuid.uuid4()
    with patch(
        "apps.backend.infrastructure.agent_artifacts_store.get_artifact",
        return_value={
            "content": {"high_paths": ["plugins/tools/x.py"]},
        },
    ):
        paths = load_delegate_allowed_paths(tenant_id=1, artifact_refs=[str(aid)])
    assert paths == ["plugins/tools/x.py"]
