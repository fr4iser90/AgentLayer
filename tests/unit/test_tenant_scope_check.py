"""tenant_scope check: what it flags, what it must not flag.

The gate only blocks on *unscoped* statements. Everything the scan cannot see
through (f-string clauses, concatenation cut-offs) is deliberately demoted to
"unresolved" so the check stays trustworthy enough to keep switched on.
"""

from __future__ import annotations

import sys
from pathlib import Path

_CHECKS_ROOT = Path(__file__).resolve().parents[2] / "scripts" / "checks"
if str(_CHECKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHECKS_ROOT))

from checks.tenant_scope import scan_text  # noqa: E402

TABLES = ["chat_conversations", "users", "todos", "agent_tasks"]
REL = Path("sample.py")


def _scan(source: str):
    return scan_text(REL, source, TABLES)


def test_unscoped_select_is_a_violation() -> None:
    out = _scan('rows = cur.execute("SELECT * FROM chat_conversations WHERE id = %s", (cid,))')
    assert len(out.violations) == 1
    assert out.violations[0].table == "chat_conversations"
    assert out.unresolved == []


def test_scoped_select_is_clean() -> None:
    out = _scan(
        'rows = cur.execute('
        '"SELECT * FROM chat_conversations WHERE id = %s AND tenant_id = %s", (cid, tid))'
    )
    assert out.violations == []
    assert out.unresolved == []


def test_site_wide_marker_on_previous_line_suppresses() -> None:
    out = _scan(
        "# tenant-scope: site-wide — instance admin roster\n"
        'cur.execute("SELECT count(*) FROM users")'
    )
    assert out.violations == []
    assert out.unresolved == []


def test_site_wide_marker_trailing_on_same_line_suppresses() -> None:
    out = _scan('cur.execute("SELECT count(*) FROM users")  # tenant-scope: site-wide')
    assert out.violations == []
    assert out.unresolved == []


def test_fstring_interpolation_is_unresolved_not_blocking() -> None:
    out = _scan('cur.execute(f"SELECT * FROM agent_tasks WHERE {clause}", params)')
    assert out.violations == []
    assert len(out.unresolved) == 1
    assert out.unresolved[0].unresolved is True


def test_concatenated_dangling_where_is_unresolved() -> None:
    out = _scan('sql = "DELETE FROM agent_tasks WHERE " + clause')
    assert out.violations == []
    assert len(out.unresolved) == 1


def test_prose_mentioning_a_table_is_not_flagged() -> None:
    out = _scan('msg = "Update todos as you progress and keep them current."')
    assert out.violations == []
    assert out.unresolved == []


def test_docstring_mentioning_a_table_is_not_flagged() -> None:
    out = _scan('def f():\n    """Read rows from chat_conversations for the user."""\n    return 1\n')
    assert out.violations == []
    assert out.unresolved == []


def test_update_with_set_is_flagged() -> None:
    out = _scan('SQL = "UPDATE users SET capabilities = %s WHERE id = %s"')
    assert len(out.violations) == 1
    assert out.violations[0].table == "users"


def test_delete_from_is_flagged() -> None:
    out = _scan('SQL = "DELETE FROM agent_tasks WHERE status = %s"')
    assert len(out.violations) == 1
    assert out.violations[0].table == "agent_tasks"


def test_join_is_flagged() -> None:
    out = _scan(
        'SQL = "SELECT c.id FROM chat_conversations c JOIN users u ON u.id = c.user_id '
        'WHERE c.user_id = %s"'
    )
    assert len(out.violations) == 1


def test_substring_of_other_identifier_is_not_flagged() -> None:
    # `users` must not match inside `tenant_users_export`.
    out = _scan('SQL = "SELECT * FROM tenant_users_export WHERE id = %s"')
    assert out.violations == []
    assert out.unresolved == []


def test_non_python_source_is_ignored_not_crashing() -> None:
    out = _scan("this is not python (( )")
    assert out.violations == []
    assert out.unresolved == []


def test_multiple_statements_report_each_once() -> None:
    out = _scan(
        'A = "SELECT * FROM users WHERE id = %s"\n'
        'B = "SELECT * FROM chat_conversations WHERE id = %s"\n'
    )
    assert len(out.violations) == 2
    assert {v.table for v in out.violations} == {"users", "chat_conversations"}
