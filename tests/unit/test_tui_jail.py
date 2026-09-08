"""Path jail and bind-root refusals for the TUI local executor (ADR 0009)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentlayer_tui.jail import JailError, bind_refusal_reason, resolve_under_root


def test_relative_path_stays_inside(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n")
    resolved = resolve_under_root(tmp_path, "src/a.py")
    assert resolved == (tmp_path / "src" / "a.py").resolve()


def test_dot_is_the_root(tmp_path: Path) -> None:
    assert resolve_under_root(tmp_path, ".") == tmp_path.resolve()
    assert resolve_under_root(tmp_path, "") == tmp_path.resolve()


def test_parent_escape_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(JailError, match="inside the workspace"):
        resolve_under_root(tmp_path, "../secret")


def test_absolute_path_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(JailError, match="absolute"):
        resolve_under_root(tmp_path, "/etc/passwd")


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-jail"
    outside.mkdir(exist_ok=True)
    (outside / "secret.txt").write_text("nope")
    link = tmp_path / "escape"
    link.symlink_to(outside)
    with pytest.raises(JailError, match="inside the workspace"):
        resolve_under_root(tmp_path, "escape/secret.txt")


def test_bind_refuses_home_and_root() -> None:
    assert bind_refusal_reason(Path.home()) is not None
    assert "home" in (bind_refusal_reason(Path.home()) or "").lower()
    assert bind_refusal_reason(Path("/")) is not None
    assert bind_refusal_reason(Path("/etc")) is not None
    assert bind_refusal_reason(Path("/usr")) is not None


def test_bind_allows_a_project_directory(tmp_path: Path) -> None:
    assert bind_refusal_reason(tmp_path) is None


def test_bind_refuses_missing_and_non_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert bind_refusal_reason(missing) is not None
    file = tmp_path / "file.txt"
    file.write_text("x")
    assert "not a directory" in (bind_refusal_reason(file) or "")


def test_tui_app_imports_the_jail() -> None:
    """Regression: /bind --local crashed with NameError after the index-consent import shuffle."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "apps/tui/agentlayer_tui/app.py"
    text = src.read_text(encoding="utf-8")
    assert "from .jail import bind_refusal_reason" in text
    assert "ALLOW_SELECT = True" in text
