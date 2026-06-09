"""coding_plan broad search guard and SSC scan artifact handoff."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from apps.backend.domain.coding_plan_search_policy import coding_plan_coding_search_blocked


def test_blocks_unscoped_search() -> None:
    msg = coding_plan_coding_search_blocked({"query": "subprocess"})
    assert msg is not None
    assert "path_prefix" in msg


def test_blocks_shallow_path_prefix() -> None:
    for prefix in ("apps", "plugins", "scripts"):
        msg = coding_plan_coding_search_blocked(
            {"query": "shell=True", "path_prefix": prefix},
        )
        assert msg is not None
        assert "too broad" in msg


def test_blocks_root_path_prefix() -> None:
    msg = coding_plan_coding_search_blocked({"query": "foo", "path_prefix": "."})
    assert msg is not None


def test_allows_scoped_search() -> None:
    assert (
        coding_plan_coding_search_blocked(
            {"query": "subprocess", "path_prefix": "apps/backend/domain"}
        )
        is None
    )


def test_git_forensics_blocks_search_before_diff() -> None:
    from apps.backend.domain.coding_plan_search_policy import coding_plan_tool_blocked

    ctx = {"agent_plan_delegate_mode": "git_forensics"}
    msg = coding_plan_tool_blocked(
        "search",
        {"query": "shell=True", "path_prefix": "plugins/tools/capabilities/coding"},
        ctx,
    )
    assert msg is not None
    assert "diff_stat" in msg
    ctx["plan_git_diff_seen"] = True
    assert (
        coding_plan_tool_blocked(
            "search",
            {"query": "shell=True", "path_prefix": "plugins/tools/capabilities/coding"},
            ctx,
        )
        is None
    )


def test_git_forensics_blocks_retrieve_context() -> None:
    from apps.backend.domain.coding_plan_search_policy import coding_plan_tool_blocked

    msg = coding_plan_tool_blocked(
        "retrieve_context",
        {"query": "SQL injection"},
        {"agent_plan_delegate_mode": "git_forensics"},
    )
    assert msg is not None
    assert "git_forensics" in msg


def test_plan_denies_bash_and_edit_tools() -> None:
    from apps.backend.domain.coding_plan_search_policy import coding_plan_tool_blocked

    for tool in (
        "bash",
        "git_sync",
        "write_file",
        "edit",
        "replace",
        "apply_patch",
    ):
        msg = coding_plan_tool_blocked(tool, {"command": "git pull"})
        assert msg is not None
        assert "read-only" in msg.lower()
        assert tool in msg


def test_infer_git_forensics_from_prompt() -> None:
    from apps.backend.domain.agent_task_prompt import infer_plan_delegate_mode

    assert infer_plan_delegate_mode("Verify branch and commits on security/fix-high-issues") == "git_forensics"


def test_semantic_search_same_rule() -> None:
    from apps.backend.domain.coding_plan_search_policy import coding_plan_search_blocked

    assert coding_plan_search_blocked("semantic_search", {"query": "auth flow"}) is not None
    assert (
        coding_plan_search_blocked(
            "semantic_search",
            {"query": "auth flow", "path_prefix": "apps/backend"},
        )
        is None
    )


def test_ssc_artifact_dedupes_per_scan_id() -> None:
    from apps.backend.domain.ssc_scan_artifact import maybe_persist_ssc_scan_artifact

    uid = uuid.uuid4()
    ctx: dict = {"user": type("U", (), {"id": uid})()}
    findings = [
        {"path": "apps/foo.py", "line": 10, "severity": "HIGH", "message": "x"},
    ]
    with patch(
        "apps.backend.infrastructure.agent_artifacts_store.create_artifact",
        return_value={"id": uuid.uuid4()},
    ) as create:
        with patch(
            "apps.backend.infrastructure.db.db.user_tenant_id",
            return_value=1,
        ):
            a1 = maybe_persist_ssc_scan_artifact(
                ctx, scan_id="scan-1", findings=findings, summary={"high": 1}
            )
            a2 = maybe_persist_ssc_scan_artifact(
                ctx, scan_id="scan-1", findings=findings, summary={"high": 1}
            )
    assert a1 == a2
    assert create.call_count == 1


def test_enrich_delegate_git_forensics_mode() -> None:
    from apps.backend.domain.agent_task_prompt import enrich_delegate_prompt

    out = enrich_delegate_prompt(
        tenant_id=1,
        base_prompt="Check branch",
        requirements=["mode: git_forensics", "No grep"],
    )
    assert "git_forensics" in out
    assert "git_read" in out
    assert "search" in out
    assert "retrieve_context" in out
