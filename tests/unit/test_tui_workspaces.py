"""Unit tests for ``/workspace``, ``/bind`` and ``/index`` rendering and matching.

The payload keys asserted here are the ones the live API returns: workspace rows come from
``workspace_row_to_api`` (see ``/v1/workspaces``) and the status block from
``workspace_retrieval.index_status_payload`` (``/v1/workspaces/{id}/index/status``).
"""

from __future__ import annotations

from agentlayer_tui import commands
from agentlayer_tui.workspaces import (
    format_index_status,
    format_workspace_rows,
    normalize_index_mode,
    resolve_workspace,
    short_id,
)

ROWS = [
    {
        "id": "a5048349-3786-4eac-9b09-aad9ca665696",
        "name": "login-investigation",
        "git_branch": "main",
        "git_url": "https://example.test/login.git",
        "source": "git",
        "semantic_index_enabled": True,
        "retrieval_enabled": True,
        "docs_rag_enabled": True,
        "graph_index_enabled": False,
        "last_index_at": "2026-09-01T10:00:00Z",
    },
    {
        "id": "3274b477-7d59-4073-947b-b3b31051eb59",
        "name": "my_workspace",
        "git_branch": "main",
        "source": "manual",
        "semantic_index_enabled": True,
        "retrieval_enabled": False,
        "last_index_at": None,
    },
    {
        "id": "26197f13-8def-45d7-bdfb-ac1ba26a0fa8",
        "name": "probe-clickshim",
        "git_branch": "feature/x",
        "source": "manual",
    },
]


class TestResolve:
    def test_full_id_wins(self) -> None:
        match, candidates = resolve_workspace(ROWS, ROWS[1]["id"])
        assert match is ROWS[1]
        assert candidates == []

    def test_exact_name(self) -> None:
        match, _ = resolve_workspace(ROWS, "my_workspace")
        assert match is ROWS[1]

    def test_name_is_case_insensitive(self) -> None:
        match, _ = resolve_workspace(ROWS, "My_Workspace")
        assert match is ROWS[1]

    def test_id_prefix(self) -> None:
        match, _ = resolve_workspace(ROWS, "3274b477")
        assert match is ROWS[1]

    def test_name_substring(self) -> None:
        match, _ = resolve_workspace(ROWS, "clickshim")
        assert match is ROWS[2]

    def test_ambiguous_returns_candidates_instead_of_guessing(self) -> None:
        rows = ROWS + [{"id": "9" * 36, "name": "probe-other"}]
        match, candidates = resolve_workspace(rows, "probe")
        assert match is None
        assert {r["name"] for r in candidates} == {"probe-clickshim", "probe-other"}

    def test_unknown_query(self) -> None:
        assert resolve_workspace(ROWS, "nope") == (None, [])

    def test_empty_query(self) -> None:
        assert resolve_workspace(ROWS, "   ") == (None, [])

    def test_exact_name_beats_being_a_substring_of_another(self) -> None:
        rows = [{"id": "1" * 36, "name": "api"}, {"id": "2" * 36, "name": "api-gateway"}]
        match, _ = resolve_workspace(rows, "api")
        assert match is rows[0]


class TestListRendering:
    def test_bound_workspace_is_marked_and_others_are_not(self) -> None:
        lines = format_workspace_rows(ROWS, bound_id=ROWS[1]["id"])
        bound = next(line for line in lines if "my_workspace" in line)
        other = next(line for line in lines if "login-investigation" in line)
        assert bound.startswith("\u2192")
        assert not other.startswith("\u2192")

    def test_shows_branch_flags_and_index_state(self) -> None:
        lines = format_workspace_rows(ROWS)
        first = next(line for line in lines if "login-investigation" in line)
        assert short_id(ROWS[0]["id"]) in first
        assert "main" in first
        assert "srd-" in first  # semantic, retrieval, docs on; graph off
        assert "indexed" in first
        second = next(line for line in lines if "my_workspace" in line)
        assert "not indexed" in second
        assert "s--" in second

    def test_empty_list_points_at_create(self) -> None:
        assert "create" in format_workspace_rows([])[0]


class TestIndexStatus:
    def test_reports_why_the_index_is_stale(self) -> None:
        lines = format_index_status(
            {
                "ok": True,
                "index_stale": True,
                "index_stale_reason": "never indexed",
                "files_out_of_date": 12,
                "last_index_at": None,
                "index_on_write_effective": "debounced",
                "qdrant": {"configured": True, "reachable": True, "collection": "code_symbols"},
                "embedding": {"configured": True, "enabled": True, "embedding_dim": 768},
                "semantic_index_enabled": True,
                "graph_index_enabled": False,
            }
        )
        blob = "\n".join(lines)
        assert "stale" in blob
        assert "never indexed" in blob
        assert "12 file(s) behind" in blob
        assert "never" in blob
        assert "code_symbols" in blob
        assert "768d" in blob
        assert f"semantic {chr(0x2713)}" in blob
        assert f"graph {chr(0x2717)}" in blob

    def test_surfaces_the_last_error(self) -> None:
        lines = format_index_status(
            {"ok": True, "last_index_at": "2026-09-01", "last_index_error": "qdrant refused"}
        )
        assert any("qdrant refused" in line for line in lines)

    def test_running_job_progress(self) -> None:
        lines = format_index_status(
            {"ok": True, "index_job": {"running": True, "files_done": 40, "files_total": 500}}
        )
        assert any("40/500 files" in line for line in lines)

    def test_not_ok_payload_does_not_pretend_to_have_a_status(self) -> None:
        lines = format_index_status({"ok": False, "error": "workspace not found"})
        assert lines == ["index status unavailable: workspace not found"]

    def test_unreachable_store_is_marked_failed(self) -> None:
        lines = format_index_status(
            {"ok": True, "qdrant": {"configured": True, "reachable": False}}
        )
        assert f"qdrant {chr(0x2717)}" in "\n".join(lines)


class TestIndexMode:
    def test_default_is_full(self) -> None:
        assert normalize_index_mode("") == "full"

    def test_known_modes(self) -> None:
        assert normalize_index_mode("code") == "code"
        assert normalize_index_mode(" DOCS ") == "docs"

    def test_unknown_mode_is_rejected_rather_than_defaulted(self) -> None:
        assert normalize_index_mode("everything") is None


class TestCommandSurface:
    def test_workspace_commands_are_listed_and_completable(self) -> None:
        for name in ("workspace", "bind", "index"):
            assert name in commands.COMMANDS
            assert f"/{name}" in commands.completions(f"/{name[:3]}")

    def test_help_mentions_them(self) -> None:
        blob = "\n".join(commands.help_lines())
        assert "/bind" in blob
        assert "/index" in blob
