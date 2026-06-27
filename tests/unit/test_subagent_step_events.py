"""Sub-agent tool step forwarding for live run cards."""

from __future__ import annotations

from apps.backend.application.agent_runtime.runtime.embedded_subagent import _forward_subagent_tool_event


def test_forward_tool_start_includes_summary() -> None:
    out: list[dict] = []

    def notify(payload: dict) -> None:
        out.append(payload)

    _forward_subagent_tool_event(
        notify,
        sub_run_id="abc",
        agent_id="coding",
        ev={
            "type": "agent.tool_start",
            "name": "read_file",
            "round": 3,
            "summary": "path=apps/backend/infrastructure/friends_db.py",
        },
    )
    assert len(out) == 1
    ev = out[0]
    assert ev["type"] == "agent.subagent_step"
    assert ev["phase"] == "start"
    assert ev["tool"] == "read_file"
    assert ev["subagent_run_id"] == "abc"
    assert "friends_db.py" in ev["summary"]


def test_forward_tool_done_omits_summary() -> None:
    out: list[dict] = []

    def notify(payload: dict) -> None:
        out.append(payload)

    _forward_subagent_tool_event(
        notify,
        sub_run_id="abc",
        agent_id="coding",
        ev={"type": "agent.tool_done", "name": "read_file", "round": 3},
    )
    assert out[0]["phase"] == "done"
    assert "summary" not in out[0]


def test_forward_tool_done_includes_failure_from_result() -> None:
    out: list[dict] = []

    def notify(payload: dict) -> None:
        out.append(payload)

    _forward_subagent_tool_event(
        notify,
        sub_run_id="abc",
        agent_id="coding",
        ev={
            "type": "agent.tool_done",
            "name": "git_push",
            "round": 2,
            "result_ok": False,
            "result_error": "[Errno 13] Permission denied: '/tmp/al-git-ask-x.sh'",
        },
    )
    assert out[0]["phase"] == "done"
    assert out[0]["ok"] is False
    assert "Permission denied" in out[0]["error"]


def test_forward_ignores_other_events() -> None:
    out: list[dict] = []

    def notify(payload: dict) -> None:
        out.append(payload)

    _forward_subagent_tool_event(
        notify,
        sub_run_id="abc",
        agent_id="coding",
        ev={"type": "agent.llm_round", "round": 1},
    )
    assert out == []


def test_forward_deferred_wait_to_parent() -> None:
    out: list[dict] = []

    def notify(payload: dict) -> None:
        out.append(payload)

    _forward_subagent_tool_event(
        notify,
        sub_run_id="sub-1",
        agent_id="security_auditor",
        ev={
            "type": "agent.deferred_wait",
            "phase": "started",
            "wait_id": "scan-abc",
            "wait_label": "security_scan",
        },
    )
    assert len(out) == 1
    assert out[0]["type"] == "agent.deferred_wait"
    assert out[0]["phase"] == "started"
    assert out[0]["subagent_run_id"] == "sub-1"
    assert out[0]["agent_id"] == "security_auditor"
