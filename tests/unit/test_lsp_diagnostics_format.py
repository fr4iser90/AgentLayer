"""Unit tests for LSP diagnostics formatting (no live language server)."""

from __future__ import annotations

from pathlib import Path

from plugins.tools.workspace.lib.lsp_client import (
    format_diagnostics_payload,
    format_one_diagnostic,
)


def test_format_one_diagnostic_one_based_and_severity() -> None:
    raw = {
        "severity": 1,
        "message": "Name \"x\" is not defined",
        "source": "Pyright",
        "code": "reportUndefinedVariable",
        "range": {
            "start": {"line": 11, "character": 4},
            "end": {"line": 11, "character": 5},
        },
    }
    item = format_one_diagnostic(raw, path="src/app.py")
    assert item["path"] == "src/app.py"
    assert item["severity"] == "error"
    assert item["line"] == 12
    assert item["character"] == 5
    assert item["end_line"] == 12
    assert item["end_character"] == 6
    assert item["code"] == "reportUndefinedVariable"
    assert item["source"] == "Pyright"


def test_format_diagnostics_payload_summary_sort_and_relative_path(tmp_path: Path) -> None:
    root = tmp_path
    file_path = root / "pkg" / "mod.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("x\n", encoding="utf-8")
    uri = file_path.resolve().as_uri()
    raw_by_uri = {
        uri: [
            {
                "severity": 2,
                "message": "unused",
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}},
            },
            {
                "severity": 1,
                "message": "boom",
                "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 1}},
            },
        ]
    }
    payload = format_diagnostics_payload(
        raw_by_uri,
        workspace_root=root,
        requested_path="pkg/mod.py",
        language="python",
        server_command=["pyright-langserver", "--stdio"],
        max_items=40,
    )
    assert payload["ok"] is True
    assert payload["summary"]["error"] == 1
    assert payload["summary"]["warning"] == 1
    assert payload["summary"]["total"] == 2
    assert payload["diagnostics"][0]["severity"] == "error"
    assert payload["diagnostics"][0]["path"] == "pkg/mod.py"
    assert payload["diagnostics"][0]["line"] == 3
    assert "file://" not in payload["diagnostics"][0]["path"]
    assert "hint" in payload
    assert payload["server"] == ["pyright-langserver", "--stdio"]


def test_format_diagnostics_payload_truncation() -> None:
    raw_by_uri = {
        "file:///tmp/x.py": [
            {
                "severity": 1,
                "message": f"e{i}",
                "range": {"start": {"line": i, "character": 0}, "end": {"line": i, "character": 1}},
            }
            for i in range(5)
        ]
    }
    payload = format_diagnostics_payload(
        raw_by_uri,
        workspace_root=None,
        requested_path="x.py",
        max_items=2,
    )
    assert payload["truncated"] is True
    assert len(payload["diagnostics"]) == 2
    assert payload["summary"]["total"] == 5
    assert "truncation_hint" in payload


def test_lsp_server_cmd_override(monkeypatch) -> None:
    from apps.backend.infrastructure.platform import config as cfg

    monkeypatch.setenv("AGENT_LSP_PYTHON_CMD", "pyright-langserver --stdio")
    assert cfg.lsp_server_cmd_override("python") == ["pyright-langserver", "--stdio"]
    monkeypatch.delenv("AGENT_LSP_PYTHON_CMD", raising=False)
    assert cfg.lsp_server_cmd_override("python") is None
