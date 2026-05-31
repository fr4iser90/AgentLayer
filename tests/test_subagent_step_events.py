"""Sub-agent tool step forwarding for live run cards."""

from __future__ import annotations

from apps.backend.domain.embedded_subagent import _forward_subagent_tool_event


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
