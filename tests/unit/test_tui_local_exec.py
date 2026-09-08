"""Local executor payloads for client-side workspace tools."""

from __future__ import annotations

import json
from pathlib import Path

from agentlayer_tui.local_exec import ADVERTISED_TOOLS, GATED_TOOLS, execute


def _load(raw: str) -> dict:
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload


def test_read_and_list(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hi\n")
    out = _load(execute("read_file", {"path": "README.md"}, tmp_path))
    assert out["ok"] is True
    assert "# hi" in out["content"]
    listed = _load(execute("list_dir", {"path": "."}, tmp_path))
    assert listed["ok"] is True
    names = {e["name"] for e in listed["entries"]}
    assert "README.md" in names


def test_read_rejects_escape(tmp_path: Path) -> None:
    out = _load(execute("read_file", {"path": "../x"}, tmp_path))
    assert out["ok"] is False
    assert "inside" in out["error"]


def test_write_replace_and_credential_block(tmp_path: Path) -> None:
    out = _load(execute("write_file", {"path": "a.txt", "content": "one two one"}, tmp_path))
    assert out["ok"] is True
    replaced = _load(
        execute(
            "replace",
            {"path": "a.txt", "old_string": "one", "new_string": "ONE", "replace_all": True},
            tmp_path,
        )
    )
    assert replaced["ok"] is True
    assert (tmp_path / "a.txt").read_text() == "ONE two ONE"
    blocked = _load(execute("write_file", {"path": ".env", "content": "SECRET=1"}, tmp_path))
    assert blocked["ok"] is False
    assert "credential" in blocked["error"].lower() or ".env" in blocked["error"]


def test_search_and_glob(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def hello():\n    return 1\n")
    found = _load(execute("search", {"query": "hello"}, tmp_path))
    assert found["ok"] is True
    assert found["count"] >= 1
    globs = _load(execute("glob", {"pattern": "**/*.py"}, tmp_path))
    assert globs["ok"] is True
    assert any(p.endswith("app.py") for p in globs["files"])


def test_bash_is_jailed_and_blocklisted(tmp_path: Path) -> None:
    (tmp_path / "ok.txt").write_text("yes\n")
    ok = _load(execute("bash", {"command": "ls"}, tmp_path))
    assert ok["ok"] is True
    assert "ok.txt" in ok["output"]
    blocked = _load(execute("bash", {"command": "rm -rf /"}, tmp_path))
    assert blocked["ok"] is False
    assert "blocked" in blocked["error"]
    escaped = _load(execute("bash", {"command": "pwd", "workdir": ".."}, tmp_path))
    assert escaped["ok"] is False


def test_unsupported_name(tmp_path: Path) -> None:
    out = _load(execute("retrieve_context", {"query": "x"}, tmp_path))
    assert out == {"ok": False, "error": "unsupported"}


def test_advertised_set_matches_the_adr() -> None:
    assert "read_file" in ADVERTISED_TOOLS
    assert "bash" in ADVERTISED_TOOLS
    assert GATED_TOOLS <= ADVERTISED_TOOLS
    assert "read_file" not in GATED_TOOLS
