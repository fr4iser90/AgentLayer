"""Workspace path containment for the agent-facing file tools.

These tools previously did ``resolved = (root / rel).resolve()`` with no
containment test. ``Path.__truediv__`` discards its left operand when the right
one is absolute, so an absolute ``path`` argument dropped the workspace root
entirely and the tool read or wrote anywhere the process could reach — across
tenant boundaries, since every workspace lives under one uid with no OS-level
separation.

The tests are deliberately driven through the real tool functions rather than
the helper, because the bug was not in a missing helper — the correct resolver
already existed three times over. The bug was tools not calling it.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from plugins.tools.workspace.files import apply_patch as ap
from plugins.tools.workspace.files import edit as ed
from plugins.tools.workspace.files import glob as gl
from plugins.tools.workspace.files import list_dir as ld
from plugins.tools.workspace.files import read_file as rf
from plugins.tools.workspace.files import replace as rp
from plugins.tools.workspace.files import write_file as wf
from plugins.tools.workspace.lib.common import WorkspacePathEscape
from plugins.tools.workspace.search import search as ss

ABSOLUTE = "/etc/hostname"
TRAVERSAL = "../../../../../../etc/hostname"

# (tool name, callable, whether it writes)
TOOLS = [
    ("coding_read_file", lambda root, p: rf.read_file({"path": p}, _ctx(root)), False),
    ("coding_list_dir", lambda root, p: ld.list_dir({"path": p}, _ctx(root)), False),
    ("coding_glob", lambda root, p: gl.glob({"pattern": "*", "path": p}, _ctx(root)), False),
    ("coding_write_file", lambda root, p: wf.write_file({"path": p, "content": "x"}, _ctx(root)), True),
    (
        "coding_replace",
        lambda root, p: rp.replace({"path": p, "old_string": "a", "new_string": "b"}, _ctx(root)),
        True,
    ),
    (
        "coding_edit",
        lambda root, p: ed.edit({"path": p, "old_string": "a", "new_string": "b"}, _ctx(root)),
        True,
    ),
    (
        "coding_apply_patch",
        lambda root, p: ap.apply_patch({"patch": _patch_for(p)}, _ctx(root)),
        True,
    ),
    ("coding_search", lambda root, p: ss.search({"query": "x", "path_prefix": p}, _ctx(root)), False),
]


def _ctx(root: Path) -> dict:
    return {"workspace": {"path": str(root), "id": "w-1", "execution_mode": "server"}}


def _patch_for(p: str) -> str:
    """A patch whose ``diff --git`` header names *p* on the ``b/`` side.

    The parser opens a file section only on ``diff --git`` and ignores the
    ``--- ``/``+++ `` pair, so a patch built from those two lines alone never
    reaches the path handling at all.
    """
    return (
        f"diff --git a/target b/{p}\n"
        f"--- a/target\n"
        f"+++ b/{p}\n"
        f"@@ -0,0 +1 @@\n+pwned\n"
    )


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    (tmp_path / "ok.txt").write_text("inside\n")
    return tmp_path


@pytest.mark.parametrize("name,call,_writes", TOOLS)
@pytest.mark.parametrize("escape", [ABSOLUTE, TRAVERSAL])
def test_tool_refuses_path_outside_the_workspace(name, call, _writes, escape, ws):
    with pytest.raises(WorkspacePathEscape):
        call(ws, escape)


@pytest.mark.parametrize("name,call,_writes", TOOLS)
def test_tool_refuses_a_symlink_out_of_the_workspace(name, call, _writes, ws):
    link = ws / "escape_link"
    try:
        os.symlink("/etc", str(link))
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this platform")
    with pytest.raises(WorkspacePathEscape):
        call(ws, "escape_link")


@pytest.mark.parametrize("name,call,writes", TOOLS)
def test_a_refused_write_created_nothing_outside(name, call, writes, ws):
    """Rejection must be rejection, not a partial write."""
    outside = Path("/tmp/qwen_containment_probe.txt")
    if outside.exists():
        outside.unlink()
    target = "../" + outside.name
    try:
        call(ws, target)
    except WorkspacePathEscape:
        pass
    assert not outside.exists(), f"{name} wrote outside the workspace despite refusing"


@pytest.mark.parametrize(
    "name,call,writes",
    [
        ("coding_read_file", lambda root, p: rf.read_file({"path": p}, _ctx(root)), False),
        ("coding_list_dir", lambda root, p: ld.list_dir({"path": p}, _ctx(root)), False),
        ("coding_glob", lambda root, p: gl.glob({"pattern": "*.txt", "path": "."}, _ctx(root)), False),
        ("coding_write_file", lambda root, p: wf.write_file({"path": p, "content": "y"}, _ctx(root)), True),
    ],
)
def test_legitimate_relative_paths_still_work(name, call, writes, ws):
    out = json.loads(call(ws, "ok.txt" if name != "coding_list_dir" and name != "coding_glob" else "."))
    assert out.get("ok") is True, f"{name} broke on a legitimate path: {out}"


def test_write_then_read_roundtrip_inside_the_workspace(ws):
    w = json.loads(wf.write_file({"path": "made.txt", "content": "hello"}, _ctx(ws)))
    assert w.get("ok") is True
    r = json.loads(rf.read_file({"path": "made.txt"}, _ctx(ws)))
    assert r.get("ok") is True
    assert "hello" in (r.get("content") or "")


def test_replace_and_edit_still_work_on_a_real_file(ws):
    (ws / "target.txt").write_text("alpha\n")
    r = json.loads(rp.replace({"path": "target.txt", "old_string": "alpha", "new_string": "beta"}, _ctx(ws)))
    assert r.get("ok") is True, r
    assert "beta" in (ws / "target.txt").read_text()

    e = json.loads(ed.edit({"path": "target.txt", "old_string": "beta", "new_string": "gamma"}, _ctx(ws)))
    assert e.get("ok") is True, e
    assert "gamma" in (ws / "target.txt").read_text()


def test_search_still_works_with_a_relative_prefix(ws):
    out = json.loads(ss.search({"query": "inside", "path_prefix": "."}, _ctx(ws)))
    assert out.get("ok") is True, out


def test_the_escape_error_is_actionable(ws):
    """The message has to tell the model what to do instead of just failing."""
    with pytest.raises(WorkspacePathEscape) as exc:
        rf.read_file({"path": ABSOLUTE}, _ctx(ws))
    msg = str(exc.value)
    assert "outside the bound workspace" in msg
    assert "relative" in msg


def test_apply_patch_still_applies_a_normal_patch(ws):
    (ws / "src").mkdir()
    (ws / "src" / "app.py").write_text("one\ntwo\n")
    patch = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n one\n-two\n+TWO\n"
    )
    out = json.loads(ap.apply_patch({"patch": patch}, _ctx(ws)))
    assert out.get("ok") is True, out
    assert (ws / "src" / "app.py").read_text() == "one\nTWO\n"


def test_context_lines_survive_a_patch(ws):
    """A patch that adds one line must not delete the unchanged lines around it."""
    (ws / "ctx.txt").write_text("a\nb\nc\nd\n")
    patch = (
        "diff --git a/ctx.txt b/ctx.txt\n"
        "--- a/ctx.txt\n+++ b/ctx.txt\n"
        "@@ -1,4 +1,5 @@\n a\n-b\n+B\n c\n+d\n d\n"
    )
    out = json.loads(ap.apply_patch({"patch": patch}, _ctx(ws)))
    assert out.get("ok") is True, out
    assert (ws / "ctx.txt").read_text() == "a\nB\nc\nd\nd\n"


def test_the_diff_prefix_is_stripped_as_a_prefix_not_a_character_set():
    """``lstrip("b/")`` ate real ``b*`` directory names and leading slashes.

    Both halves matter for containment: eating a leading slash made an absolute
    path look relative, so the resolver never saw what the patch really named.
    """
    assert ap._path_from_diff_token("b/src/app.py", "b") == "src/app.py"
    assert ap._path_from_diff_token("b/b/data.csv", "b") == "b/data.csv"
    assert ap._path_from_diff_token("b//etc/hostname", "b") == "/etc/hostname"
    assert ap._path_from_diff_token("b/../escape", "b") == "../escape"
    assert ap._path_from_diff_token("a/src/app.py", "a") == "src/app.py"


def test_the_patch_targets_the_b_side_of_the_diff_header():
    """The old code read ``parts[2]`` (the ``a/`` side) and never stripped it."""
    assert (
        ap._target_path_from_diff_header("diff --git a/src/app.py b/src/app.py") == "src/app.py"
    )
    assert (
        ap._target_path_from_diff_header("diff --git a/b/keep.csv b/b/keep.csv") == "b/keep.csv"
    )
    assert ap._target_path_from_diff_header("diff --git a/x b/../escape") == "../escape"


def test_apply_patch_still_targets_a_real_file_under_a_b_directory(ws):
    (ws / "b").mkdir()
    (ws / "b" / "keep.csv").write_text("old\n")
    patch = (
        "diff --git a/b/keep.csv b/b/keep.csv\n"
        "--- a/b/keep.csv\n+++ b/b/keep.csv\n"
        "@@ -1,1 +1,1 @@\n-old\n+held\n"
    )
    out = json.loads(ap.apply_patch({"patch": patch}, _ctx(ws)))
    assert out.get("ok") is True, out
    assert (ws / "b" / "keep.csv").read_text() == "held\n"
    assert not (ws / "keep.csv").exists(), "the b-directory was eaten again"
