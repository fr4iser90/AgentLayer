"""Unit tests for the TUI's event rendering — the part that breaks when the WS contract moves.

Field names here are taken from the emitting code, not invented: see
``chat_websocket.py``, ``subagent_events.py`` and ``conversation_goal_events.py``.
"""

from __future__ import annotations

import pytest

from agentlayer_tui import commands
from agentlayer_tui.client import resolve_default_model
from agentlayer_tui.events import (
    TurnState,
    answer_from_completion,
    format_duration,
    goal_strip,
    interpret,
    tool_label,
)


@pytest.fixture
def state() -> TurnState:
    return TurnState()


class TestToolLines:
    def test_start_prefers_step_label_like_the_webui(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.tool_start",
                "name": "read_file",
                "step_label": "Read api/main.py",
                "round": 1,
            },
            state,
        )
        assert up.lines[0].text.endswith("Read api/main.py")
        assert up.lines[0].key == "tool:read_file:1"

    def test_label_falls_back_to_a_readable_name(self) -> None:
        assert tool_label({"name": "apply_patch"}) == "apply patch"
        assert tool_label({"name": "x", "label": "Patch"}) == "Patch"

    def test_done_reuses_the_start_label_and_same_key(self, state: TurnState) -> None:
        interpret(
            {"type": "agent.tool_start", "name": "grep", "step_label": "Search repo", "round": 2},
            state,
        )
        up = interpret(
            {
                "type": "agent.tool_done",
                "name": "grep",
                "round": 2,
                "result_ok": True,
                "result_chars": 812,
                "duration_ms": 1500,
            },
            state,
        )
        line = up.lines[0]
        assert line.key == "tool:grep:2", "done must rewrite the row the start created"
        assert "Search repo" in line.text
        assert "812 chars" in line.text and "1.5 s" in line.text

    def test_failure_is_marked_and_carries_the_error(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.tool_done",
                "name": "bash",
                "round": 1,
                "result_ok": False,
                "result_error": "exit 1",
            },
            state,
        )
        assert up.lines[0].kind == "tool_error"
        assert "failed: exit 1" in up.lines[0].text

    def test_rejected_arguments_surface_as_a_warning(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.tool_start",
                "name": "write_file",
                "round": 1,
                "rejected": True,
                "validation": {"path": "required"},
            },
            state,
        )
        kinds = [line.kind for line in up.lines]
        assert "warn" in kinds
        assert any("path: required" in line.text for line in up.lines)

    @pytest.mark.parametrize(
        ("ms", "expected"),
        [(None, ""), (-1, ""), (250, "250 ms"), (1500, "1.5 s"), (90_000, "1.5 min")],
    )
    def test_duration_formatting(self, ms: float | None, expected: str) -> None:
        assert format_duration(ms) == expected


class TestSubagents:
    def test_delegation_start_names_the_specialist(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.subagent_start",
                "subagent_run_id": "r1",
                "agent_id": "coding",
                "tool_name": "delegate",
                "detail": "fix the login bug",
            },
            state,
        )
        assert "coding" in up.lines[0].text
        assert "fix the login bug" in up.lines[0].text

    def test_subagent_steps_are_indented_under_the_parent(self, state: TurnState) -> None:
        start = interpret(
            {
                "type": "agent.subagent_step",
                "phase": "start",
                "tool": "read_file",
                "round": 1,
                "step_label": "Read auth.py",
            },
            state,
        )
        done = interpret(
            {
                "type": "agent.subagent_step",
                "phase": "done",
                "tool": "read_file",
                "round": 1,
                "ok": True,
            },
            state,
        )
        assert start.lines[0].depth == 1
        assert done.lines[0].depth == 1
        assert done.lines[0].key == start.lines[0].key
        assert "Read auth.py" in done.lines[0].text


class TestGoalLayer:
    def test_goal_event_updates_state_and_strip(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.goal",
                "goal": {
                    "objective": "Ship the health endpoint",
                    "phase": "active",
                    "rounds_started": 2,
                    "max_goal_rounds": 32,
                },
                "goal_event": "goal_create",
            },
            state,
        )
        assert up.strip_changed
        top, _ = goal_strip(state)
        assert "Ship the health endpoint" in top
        assert "round 2/32" in top

    def test_todos_use_the_server_counts(self, state: TurnState) -> None:
        interpret(
            {
                "type": "agent.todos",
                "todos": [
                    {"content": "find router", "status": "completed"},
                    {"content": "write endpoint", "status": "in_progress"},
                    {"content": "test", "status": "pending"},
                ],
                "counts": {"pending": 1, "in_progress": 1, "completed": 1},
            },
            state,
        )
        _, todos_row = goal_strip(state)
        assert todos_row.startswith("Todos 1/3")
        assert "find router" in todos_row

    def test_blocked_goal_shows_its_reason(self, state: TurnState) -> None:
        interpret(
            {
                "type": "agent.goal",
                "goal": {
                    "objective": "Migrate DB",
                    "phase": "blocked",
                    "blocked_reason": "needs credentials",
                },
            },
            state,
        )
        assert "needs credentials" in goal_strip(state)[0]

    def test_plan_mode_is_flagged_in_the_strip(self, state: TurnState) -> None:
        interpret({"type": "agent.plan_mode", "plan_mode": True}, state)
        assert "plan mode" in goal_strip(state)[0]

    def test_empty_state_renders_placeholders(self, state: TurnState) -> None:
        assert goal_strip(state) == ["Goal  —", "Todos  —"]


class TestTurnLifecycle:
    def test_deltas_accumulate_only_on_the_text_channel(self, state: TurnState) -> None:
        assert interpret({"type": "agent.llm_delta", "delta": "Hel"}, state).delta == "Hel"
        reasoning = interpret(
            {"type": "agent.llm_delta", "channel": "reasoning", "reasoning_delta": "hmm"},
            state,
        )
        assert reasoning.delta == ""
        assert reasoning.reasoning_delta == "hmm"

    def test_deltas_keep_their_whitespace(self, state: TurnState) -> None:
        """Chunk boundaries sit between words; stripping each one glues the answer together."""
        chunks = ["The", " TUI", " client", " works", "."]
        joined = "".join(interpret({"type": "agent.llm_delta", "delta": c}, state).delta
                         for c in chunks)
        assert joined == "The TUI client works."

    def test_completion_finishes_the_turn(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "chat.completion",
                "data": {"choices": [{"message": {"role": "assistant", "content": "done"}}]},
            },
            state,
        )
        assert up.finished
        assert answer_from_completion(up.completion) == "done"

    def test_error_completion_reports_the_detail(self, state: TurnState) -> None:
        up = interpret({"type": "chat.completion", "error": True, "detail": "boom"}, state)
        assert up.finished and up.error == "boom"

    def test_permission_ask_is_passed_through(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.permission_ask",
                "request_id": "abc",
                "tool_name": "bash",
                "args_preview": '{"cmd":"rm -rf /"}',
                "round": 3,
            },
            state,
        )
        assert up.permission is not None
        assert up.permission.request_id == "abc"
        assert up.permission.tool_name == "bash"

    def test_tool_invoke_is_passed_through_and_labelled_local(self, state: TurnState) -> None:
        up = interpret(
            {
                "type": "agent.tool_invoke",
                "request_id": "rid-9",
                "tool_name": "read_file",
                "arguments": {"path": "README.md"},
                "round": 1,
            },
            state,
        )
        assert up.tool_invoke is not None
        assert up.tool_invoke.request_id == "rid-9"
        assert up.tool_invoke.arguments["path"] == "README.md"
        assert up.lines and "local" in up.lines[0].text

    def test_slot_wait_becomes_a_hint_not_a_line(self, state: TurnState) -> None:
        up = interpret(
            {"type": "agent.llm_slot_wait", "waited_sec": 4, "queue_ahead": 2}, state
        )
        assert up.lines == []
        assert up.wait_hint and "2 ahead" in up.wait_hint

    def test_unknown_events_are_ignored_so_the_client_stays_compatible(
        self, state: TurnState
    ) -> None:
        up = interpret({"type": "agent.something_new_in_2027", "x": 1}, state)
        assert up.lines == [] and not up.finished

    def test_malformed_event_does_not_raise(self, state: TurnState) -> None:
        assert interpret({}, state).lines == []
        assert interpret({"type": None}, state).lines == []


class TestModelSelection:
    """The server rejects a chat with no model and publishes no default, so the client picks."""

    ROWS = [
        {"id": "tiny", "owned_by": "provider_dead"},
        {"id": "good", "owned_by": "provider_1"},
    ]

    def test_prefers_a_reachable_provider(self) -> None:
        providers = {
            "provider_dead": {"reachable": False},
            "provider_1": {"reachable": True},
        }
        assert resolve_default_model(self.ROWS, providers) == "good"

    def test_falls_back_to_the_first_model_when_none_is_reachable(self) -> None:
        assert resolve_default_model(self.ROWS, {"provider_1": {"reachable": False}}) == "tiny"

    def test_no_models_yields_no_choice(self) -> None:
        assert resolve_default_model([], {"provider_1": {"reachable": True}}) == ""

    def test_ignores_rows_without_an_id(self) -> None:
        rows = [{"owned_by": "provider_1"}, {"id": "real", "owned_by": "provider_1"}]
        assert resolve_default_model(rows, {"provider_1": {"reachable": True}}) == "real"


class TestCommands:
    def test_plain_text_is_not_a_command(self) -> None:
        assert commands.parse("hello world") is None

    def test_command_splits_name_and_args(self) -> None:
        cmd = commands.parse("/delegate coding fix the bug")
        assert cmd is not None
        assert cmd.name == "delegate"
        assert cmd.args == "coding fix the bug"

    def test_bare_slash_shows_help(self) -> None:
        cmd = commands.parse("/")
        assert cmd is not None and cmd.name == "help"

    def test_completions_filter_by_prefix(self) -> None:
        assert commands.completions("/mod") == ["/model", "/models"]
        assert commands.completions("hello") == []

    def test_delegation_prompt_names_the_agent_and_the_tool(self) -> None:
        prompt = commands.delegation_prompt("coding", "write a test")
        assert "coding" in prompt and "write a test" in prompt
        assert "delegate tool" in prompt

    def test_every_command_is_documented(self) -> None:
        assert set(commands.COMMANDS) >= {"help", "quit", "cancel", "delegate", "goal", "todos"}
        assert all(desc.strip() for desc in commands.COMMANDS.values())
