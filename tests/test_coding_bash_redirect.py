"""Tests for coding_bash → dedicated tool redirect."""

from __future__ import annotations

from plugins.tools.capabilities.coding.coding_bash_redirect import redirect_coding_bash_command


def test_redirect_ls_to_list_dir() -> None:
    out = redirect_coding_bash_command("ls -la")
    assert out == ("coding_list_dir", {"path": "."})


def test_redirect_cat_to_read_file() -> None:
    out = redirect_coding_bash_command("cat apps/backend/api/workspaces_api.py")
    assert out == ("coding_read_file", {"path": "apps/backend/api/workspaces_api.py"})


def test_redirect_head_to_read_file_with_limit() -> None:
    out = redirect_coding_bash_command("head -n 50 foo.py")
    assert out == ("coding_read_file", {"path": "foo.py", "limit_lines": 50})


def test_redirect_git_pull_to_git_sync() -> None:
    out = redirect_coding_bash_command("git pull")
    assert out == ("coding_git_sync", {"operation": "pull"})


def test_redirect_python_open_to_read_file() -> None:
    out = redirect_coding_bash_command(
        """python3 -c "f=open('apps/x.py'); print(f.read())" """
    )
    assert out == ("coding_read_file", {"path": "apps/x.py"})


def test_pipes_rejected_as_readlike() -> None:
    out = redirect_coding_bash_command("cat foo.py | head -n 5")
    assert isinstance(out, str)
    assert "coding_read_file" in out


def test_pytest_stays_bash() -> None:
    assert redirect_coding_bash_command("pytest tests/") is None
