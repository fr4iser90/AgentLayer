"""Unit tests for TUI slash suggest / tab completion."""

from __future__ import annotations

from agentlayer_tui.commands import apply_tab, format_suggest_panel, suggest


def test_suggest_lists_commands_on_slash() -> None:
    rows = suggest("/")
    assert any(r.insert.startswith("/help") for r in rows)
    assert any(r.insert.startswith("/bind") for r in rows)
    assert all(r.label.startswith("/") for r in rows)


def test_suggest_filters_by_prefix() -> None:
    rows = suggest("/co")
    names = [r.insert.strip() for r in rows]
    assert "/consent" in names
    assert "/continue" in names
    assert "/bind" not in names
    rows_ca = suggest("/ca")
    assert any(r.insert.startswith("/cancel") for r in rows_ca)


def test_suggest_arg_choices() -> None:
    rows = suggest("/plan ")
    assert {r.insert for r in rows} == {"/plan on", "/plan off"}
    rows = suggest("/consent s")
    assert rows[0].insert == "/consent symbols"
    rows = suggest("/delegate c")
    assert any(r.insert.startswith("/delegate coding") for r in rows)


def test_tab_single_and_cycle() -> None:
    value, cycle, matches = apply_tab("/hel")
    assert value == "/help "
    assert matches and matches[0].insert == "/help "

    value, cycle, matches = apply_tab("/co")
    assert value.startswith("/co")  # common prefix
    assert len(matches) >= 2
    # After prefix is filled, cycling picks concrete commands.
    filled, cycle2, _ = apply_tab(value, 0)
    assert filled.startswith("/")
    again, _, _ = apply_tab(filled if filled == value else value, cycle2 if filled == value else 0)
    assert again.startswith("/")


def test_format_suggest_panel_mentions_tab() -> None:
    text = format_suggest_panel(suggest("/"))
    assert "/agents" in text or "/bind" in text
    assert "tab" in text.lower()
