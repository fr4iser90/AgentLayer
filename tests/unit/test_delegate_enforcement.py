"""Generic delegate enforcement (Option B orchestration)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

from apps.backend.domain.delegation.enforcement import (
    coding_delegate_tool_blocked,
    delegate_excerpt_is_actionable,
    delegate_fingerprint,
    extract_handoff_artifact_ids,
    general_orchestrator_tool_blocked,
    load_delegate_allowed_paths,
    orchestrator_pre_tool_blocked,
    paths_from_artifact_content,
    record_orchestrator_delegate_success,
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


def test_reject_coding_fix_from_artifact_without_refs() -> None:
    msg = subagent_reject_reason(
        agent_id="coding",
        requirements=["mode: fix_from_artifact", "branch: security/fix"],
        artifact_refs=None,
    )
    assert msg is not None
    assert "artifact_refs" in msg


def test_fix_from_artifact_allows_read_when_no_paths() -> None:
    ctx = {"agent_delegate_mode": "fix_from_artifact", "agent_delegate_allowed_paths": []}
    assert coding_delegate_tool_blocked("search", {"query": "x"}, ctx) is None
    assert coding_delegate_tool_blocked("read_file", {"path": "apps/foo.py"}, ctx) is None
    msg = coding_delegate_tool_blocked(
        "edit",
        {"path": "apps/foo.py", "old_string": "a", "new_string": "b"},
        ctx,
    )
    assert msg is not None
    assert "no paths" in msg


def test_handoff_artifact_ids_from_delegate_payload() -> None:
    raw = '{"ok": true, "handoff_artifact_ids": ["id-1", "id-2"]}'
    assert extract_handoff_artifact_ids(raw) == ["id-1", "id-2"]


def test_load_delegate_allowed_paths() -> None:
    aid = uuid.uuid4()
    with patch(
        "apps.backend.domain.delegation.enforcement.agent_artifacts_store.get_artifact",
        return_value={
            "content": {"high_paths": ["plugins/tools/x.py"]},
        },
    ):
        paths = load_delegate_allowed_paths(tenant_id=1, artifact_refs=[str(aid)])
    assert paths == ["plugins/tools/x.py"]


def test_delegate_fingerprint_normalizes_whitespace() -> None:
    assert delegate_fingerprint("coding_plan", "  Read   file  ") == delegate_fingerprint(
        "coding_plan", "read file"
    )


def test_orchestrator_blocks_duplicate_delegate_fingerprint() -> None:
    ctx: dict = {
        "agent_id": "general",
        "orchestrator_last_delegate_excerpt": "line one",
        "orchestrator_last_delegate_excerpt_actionable": True,
        "orchestrator_delegate_success_fps": {
            delegate_fingerprint("coding_plan", "read README first line"),
        },
    }
    msg = orchestrator_pre_tool_blocked(
        "delegate",
        {
            "agent_id": "coding_plan",
            "prompt": "read README first line",
            "run_subagent": True,
        },
        ctx,
    )
    assert msg is not None
    assert "already delegated" in msg


def test_orchestrator_allows_retry_same_agent_when_excerpt_not_actionable() -> None:
    ctx: dict = {
        "agent_id": "general",
        "orchestrator_last_delegate_excerpt": "<tool_call>read_file</tool_call>",
        "orchestrator_last_delegate_excerpt_actionable": False,
        "orchestrator_last_delegate_agent_id": "coding",
    }
    msg = orchestrator_pre_tool_blocked(
        "delegate",
        {
            "agent_id": "coding",
            "prompt": "Read README.md first line only",
            "run_subagent": True,
        },
        ctx,
    )
    assert msg is None


def test_record_orchestrator_skips_fingerprint_for_markup_excerpt() -> None:
    ctx: dict = {"agent_id": "general"}
    raw = json.dumps({"ok": True, "assistant_excerpt": "<tool_call>read_file</tool_call>"})
    record_orchestrator_delegate_success(
        ctx,
        {"agent_id": "coding", "prompt": "read readme"},
        raw,
    )
    assert ctx.get("orchestrator_last_delegate_excerpt_actionable") is False
    assert "orchestrator_delegate_success_fps" not in ctx or not ctx.get(
        "orchestrator_delegate_success_fps"
    )


def test_record_orchestrator_delegate_success_tracks_fingerprint() -> None:
    ctx: dict = {"agent_id": "general"}
    raw = json.dumps({"ok": True, "assistant_excerpt": "The sum is 42."})
    record_orchestrator_delegate_success(
        ctx,
        {"agent_id": "math", "prompt": "17+25"},
        raw,
    )
    assert ctx["orchestrator_last_delegate_excerpt"] == "The sum is 42."
    assert ctx["orchestrator_last_delegate_excerpt_actionable"] is True
    assert ctx["orchestrator_last_delegate_agent_id"] == "math"
    assert delegate_fingerprint("math", "17+25") in ctx["orchestrator_delegate_success_fps"]


def test_delegate_excerpt_is_actionable_rejects_tool_markup() -> None:
    assert not delegate_excerpt_is_actionable("<tool_call>read_file</tool_call>")
    assert not delegate_excerpt_is_actionable('<invoke name="read_file">\n<parameter name="path">README.md</parameter>\n</invoke>')
    assert not delegate_excerpt_is_actionable('{"command": "head -n 1 README.md"}')
    assert not delegate_excerpt_is_actionable("The command `awk 'NF{print;exit}' README.md` will:\n- Open README.md")
    assert delegate_excerpt_is_actionable("# Hello-World")
    assert delegate_excerpt_is_actionable("README.md: Hello World!")
    assert not delegate_excerpt_is_actionable("Read README.md in Hello-World repo")
    assert not delegate_excerpt_is_actionable("[read_file]")
    assert not delegate_excerpt_is_actionable("I read the file successfully")


def test_tool_result_display_line_delegate() -> None:
    from apps.backend.domain.delegation.enforcement import tool_result_display_line

    ok_json = json.dumps(
        {"ok": True, "assistant_excerpt": "README.md: Hello World!"}
    )
    assert tool_result_display_line("delegate", ok_json) == "README.md: Hello World!"
    fail_json = json.dumps({"ok": False, "error": "sub-agent timed out"})
    assert "timed out" in (tool_result_display_line("delegate", fail_json) or "")
    assert tool_result_display_line("workspace.create", ok_json) is None
