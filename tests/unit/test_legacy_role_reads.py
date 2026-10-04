"""The legacy ``users.role`` gate: what it must flag, what it must not, and that it still bites.

Three groups:

* synthetic sources that must be reported — the reads this codebase used to contain, so a
  reintroduced one cannot land silently;
* synthetic sources that must stay clean — otherwise the gate gets worked around or switched
  off (another table's ``role``, a docstring, the shared ``ELEVATED_SQL`` fragment);
* the repository itself — clean today, with no stale exemption: every allowlisted identity file
  must still contain a paired read, and every paired read must still be allowlisted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHECKS_ROOT = _REPO_ROOT / "scripts" / "checks"
if str(_CHECKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_CHECKS_ROOT))

from checks import legacy_role_reads as gate  # noqa: E402
from checks.common import candidate_python_files  # noqa: E402

CONFIG = json.loads((_CHECKS_ROOT / "config.json").read_text(encoding="utf-8"))
CHECK_CONFIG = CONFIG["checks"]["legacy_role_reads"]
PAIR_READER_ENTRIES = CHECK_CONFIG["identity_pair_readers"]
IDENTITY_FILES = {str(entry["path"]) for entry in PAIR_READER_ENTRIES}

#: A path outside the identity layer: a paired read here is a violation.
PLAIN_REL = "apps/backend/application/sample.py"


def _scan(source: str, rel: str = PLAIN_REL) -> gate.ScanOutput:
    return gate.scan_text(Path(rel), source, identity_pair_readers=IDENTITY_FILES)


def _rules(out: gate.ScanOutput) -> list[str]:
    return [violation.rule for violation in out.violations]


# --------------------------------------------------------------------------- must be reported


def test_legacy_column_read_alone_is_flagged() -> None:
    out = _scan('cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))')
    assert _rules(out) == [gate.RULE_LEGACY_ALONE]
    assert out.violations[0].line == 1
    assert out.pair_readers == set()


def test_writing_the_legacy_column_is_flagged() -> None:
    out = _scan('cur.execute("UPDATE users SET role = %s WHERE id = %s", (role, user_id))')
    assert _rules(out) == [gate.RULE_LEGACY_ALONE]


def test_alias_qualified_legacy_read_is_flagged() -> None:
    out = _scan('cur.execute("SELECT u.id, u.role FROM users u WHERE u.id = %s", (user_id,))')
    assert _rules(out) == [gate.RULE_LEGACY_ALONE]


def test_schema_qualified_and_only_relations_are_seen() -> None:
    source = (
        'cur.execute("SELECT id, role FROM public.users WHERE id = %s", (user_id,))\n'
        'cur.execute("SELECT id, role FROM ONLY users WHERE id = %s", (user_id,))\n'
    )
    assert _rules(_scan(source)) == [gate.RULE_LEGACY_ALONE, gate.RULE_LEGACY_ALONE]


def test_paired_read_outside_the_identity_layer_is_flagged() -> None:
    out = _scan('cur.execute("SELECT site_role, role FROM users WHERE id = %s", (user_id,))')
    assert _rules(out) == [gate.RULE_PAIR_OUTSIDE_IDENTITY]
    # The file is still recorded as a pair reader — that is what the no-stale-allowlist
    # assertion below compares against, so an exemption can never be granted blindly.
    assert out.pair_readers == {PLAIN_REL}


def test_qualified_elevation_column_still_counts_as_a_pair() -> None:
    out = _scan(
        'cur.execute("SELECT u.id, u.role, u.site_role FROM users u WHERE u.id = %s", (uid,))'
    )
    assert _rules(out) == [gate.RULE_PAIR_OUTSIDE_IDENTITY]


def test_getattr_on_role_is_flagged_as_a_claim() -> None:
    out = _scan('role = getattr(user, "role")')
    assert _rules(out) == [gate.RULE_CLAIM_READ]


def test_a_file_can_be_flagged_by_both_rules() -> None:
    source = (
        'role = getattr(user, "role")\n'
        'cur.execute("SELECT id, role FROM users WHERE id = %s", (user_id,))\n'
    )
    assert sorted(_rules(_scan(source))) == sorted([gate.RULE_CLAIM_READ, gate.RULE_LEGACY_ALONE])


# ------------------------------------------------------------------------- must stay clean


def test_paired_read_in_an_identity_file_is_allowed() -> None:
    for rel in sorted(IDENTITY_FILES):
        out = _scan('cur.execute("SELECT site_role, role FROM users WHERE id = %s", (uid,))', rel)
        assert out.violations == [], rel
        assert out.pair_readers == {rel}, rel


def test_the_shared_elevated_sql_fragment_is_not_a_read() -> None:
    # Its column names live in the interpolated value, so the fragment stays the only place
    # the compatibility column is spelled out in SQL — which is the point of having one.
    source = (
        "from apps.backend.domain.identity.roles import ELEVATED_SQL\n"
        'cur.execute(f"SELECT id FROM users WHERE {ELEVATED_SQL} ORDER BY created_at")\n'
    )
    out = _scan(source)
    assert out.violations == []
    assert out.pair_readers == set()


def test_role_of_another_table_joined_against_users_is_not_reported() -> None:
    # The shape that a naive scan reports: ``role`` belongs to dashboard_members here.
    source = (
        'cur.execute(\n'
        '    "SELECT m.user_id, m.role, m.created_at, u.email "\n'
        '    "FROM dashboard_members m JOIN users u ON u.id = m.user_id"\n'
        ')\n'
    )
    out = _scan(source)
    assert out.violations == []
    assert out.pair_readers == set()


def test_prose_in_a_docstring_is_not_a_query() -> None:
    source = '"""Before ADR 0011 the code ran SELECT id, role FROM users WHERE id = %s."""\n'
    assert _scan(source).violations == []


def test_statement_on_users_without_the_legacy_column_is_clean() -> None:
    out = _scan('cur.execute("SELECT id, email, site_role FROM users WHERE id = %s", (uid,))')
    assert out.violations == []
    assert out.pair_readers == set()


def test_getattr_on_the_elevation_column_is_clean() -> None:
    assert _scan('site_role = getattr(user, "site_role")').violations == []


def test_unparseable_source_is_skipped_not_reported() -> None:
    out = _scan('cur.execute("SELECT role FROM users" )(:\n')
    assert out.violations == []
    assert out.pair_readers == set()


# ------------------------------------------------------------------- the gate still has teeth


def _scan_repository() -> tuple[list[Path], list[gate.Violation], set[str]]:
    files = candidate_python_files(_REPO_ROOT, CHECK_CONFIG)
    violations: list[gate.Violation] = []
    pair_readers: set[str] = set()
    for path in files:
        rel = path.relative_to(_REPO_ROOT)
        out = gate.scan_text(rel, path.read_text(encoding="utf-8"), identity_pair_readers=IDENTITY_FILES)
        violations.extend(out.violations)
        pair_readers |= out.pair_readers
    return files, violations, pair_readers


def test_the_repository_is_clean() -> None:
    files, violations, pair_readers = _scan_repository()
    assert len(files) > 500, f"scope collapsed to {len(files)} files — the gate scans nothing"
    assert pair_readers == IDENTITY_FILES, (
        "paired readers drifted from the allowlist: "
        f"unlisted={sorted(pair_readers - IDENTITY_FILES)} "
        f"stale={sorted(IDENTITY_FILES - pair_readers)}"
    )
    assert violations == []


def test_every_exemption_is_still_earned() -> None:
    """A file may only stay exempt while it really reads the pair."""
    _, _, pair_readers = _scan_repository()
    for entry in PAIR_READER_ENTRIES:
        assert str(entry["path"]) in pair_readers, (
            f"{entry['path']} is allowlisted but no longer reads the pair — remove the exemption"
        )
        assert str(entry.get("reason") or "").strip(), f"{entry['path']} has no reason"


def test_config_accepts_a_bare_path_entry() -> None:
    """The allowlist parses both ``{path, reason}`` and a plain path, through ``run()``."""
    target = "apps/backend/infrastructure/db/identity_tenants.py"
    config = {
        "scope": "all",
        "include": ["apps/backend/infrastructure/db"],
        "ignore": CHECK_CONFIG["ignore"],
        "identity_pair_readers": [target],
    }
    assert gate.run("legacy_role_reads", config).ok is True


def test_a_pair_reader_without_an_exemption_fails_the_run() -> None:
    """Non-vacuity on real code: the same file fails once the exemption is withdrawn."""
    config = {
        "scope": "all",
        "include": ["apps/backend/infrastructure/db"],
        "ignore": CHECK_CONFIG["ignore"],
        "identity_pair_readers": [],
    }
    assert gate.run("legacy_role_reads", config).ok is False
