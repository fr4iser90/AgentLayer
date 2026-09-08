"""Local symbol/markdown scan stays inside the TUI jail (ADR 0009 M3/M4)."""

from __future__ import annotations

from pathlib import Path

from agentlayer_tui.symbol_scan import scan_markdown, scan_symbols


def test_python_symbols_and_relative_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("def hello():\n    return 1\n\nclass Foo:\n    pass\n")
    files, errors = scan_symbols(tmp_path)
    assert errors == []
    assert len(files) == 1
    assert files[0]["path"] == "src/a.py"
    assert not files[0]["path"].startswith("/")
    names = {s["name"] for s in files[0]["symbols"]}
    assert "hello" in names
    assert "Foo" in names
    assert all(len(s.get("signature") or "") <= 200 for s in files[0]["symbols"])
    assert len(files[0]["sha256"]) == 64


def test_symlink_escape_is_skipped(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-symbol-scan"
    outside.mkdir(exist_ok=True)
    (outside / "secret.py").write_text("def leak():\n    return 0\n")
    (tmp_path / "escape").symlink_to(outside)
    (tmp_path / "ok.py").write_text("def keep():\n    pass\n")
    files, _errors = scan_symbols(tmp_path)
    paths = {f["path"] for f in files}
    assert "ok.py" in paths
    assert not any("secret" in p for p in paths)
    assert not any(p.startswith("/") for p in paths)


def test_markdown_scan_skips_dot_dirs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hello\n")
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "nope.md").write_text("# secret\n")
    docs, errors = scan_markdown(tmp_path)
    assert errors == []
    assert [d["path"] for d in docs] == ["README.md"]
    assert docs[0]["text"].startswith("# hello")
