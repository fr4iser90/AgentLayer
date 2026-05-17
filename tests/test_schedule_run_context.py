"""Tests for schedule run tool event collection."""

from __future__ import annotations

import uuid

from apps.backend.domain.schedule_run_context import (
    begin_schedule_run_collection,
    get_schedule_tool_events,
    record_schedule_tool_event,
    reset_schedule_run_collection,
)


def test_tool_events_readable_before_reset() -> None:
    run_id = uuid.uuid4()
    t1, t2 = begin_schedule_run_collection(run_id)
    record_schedule_tool_event(
        round_num=1,
        tool_name="coding_git_sync",
        args={"operation": "pull"},
        ok=True,
    )
    events = get_schedule_tool_events()
    assert len(events) == 1
    assert events[0]["name"] == "coding_git_sync"
    reset_schedule_run_collection(t1, t2)
    assert get_schedule_tool_events() == []
