"""Static gate: the legacy ``users.role`` column decides nothing (ADR 0011 §1).

``users.site_role`` is the only source of elevation. ``users.role`` survives as a
compatibility column that may speak for one row only when that row was never migrated
(``site_role IS NULL``), and the rule that reads it lives in exactly one place —
``apps/backend/domain/identity/roles.py``. This check keeps new code from touching the
column again:

* **legacy-alone** — a statement that names the ``users`` relation and mentions the legacy
  column must name ``site_role`` beside it. ``SELECT id, role FROM users`` — the
  pre-migration read — fails; a paired read can at least be judged by the domain rule.
* **pair-outside-identity** — a paired read belongs to the identity layer alone, listed in
  ``identity_pair_readers`` with a reason. Everywhere else the question is
  ``db.user_site_role(...)`` / ``db.user_effective_role(...)``: one resolver, so one place
  where the compatibility column can still answer, and removing the column later is a
  change there and nowhere else.
* **claim-read** — ``getattr(obj, "role")`` is refused outright. A role read off an
  arbitrary object is a carried claim (token payload, tool context, DTO), and a claim is
  never a source of elevation.

A column mention is bound to the ``users`` relation of its own statement: ``m.role`` beside
``JOIN users u`` belongs to another table and is none of this rule's business, while an
unqualified ``role`` in a statement that touches ``users`` is taken for the legacy column.

The shared SQL fragment ``domain.identity.roles.ELEVATED_SQL`` keeps a file clean: inside an
f-string its text is interpolated, so only the fragment's own definition names the column.

Self-verification lives in ``tests/unit/test_legacy_role_reads.py``: it drives this same
``scan_text`` with synthetic sources that must and must not be reported, and it fails if an
allowlisted file stops containing a paired read — an exemption may not outlive the code that
needed it.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import (
    CheckResult,
    candidate_python_files,
    print_fail,
    print_header,
    print_pass,
    print_skip,
    repo_root,
    string_literals,
)

LEGACY_COLUMN = "role"
ELEVATION_COLUMN = "site_role"

RULE_LEGACY_ALONE = "legacy-alone"
RULE_PAIR_OUTSIDE_IDENTITY = "pair-outside-identity"
RULE_CLAIM_READ = "claim-read"

#: ``users`` used as a relation, with its optional SQL alias.
_USERS_RELATION = re.compile(
    r"\b(?:FROM|INTO|UPDATE|JOIN)\s+(?:ONLY\s+)?(?:PUBLIC\.)?USERS\b(?:\s+(?:AS\s+)?([A-Za-z_]\w*))?",
    re.IGNORECASE,
)

#: A word right after the relation is a keyword, not an alias (``FROM users WHERE …``).
_SQL_KEYWORDS = frozenset(
    {
        "and", "as", "conflict", "cross", "delete", "do", "full", "from", "group", "inner",
        "insert", "is", "join", "lateral", "left", "limit", "not", "null", "offset", "on",
        "only", "order", "or", "public", "returning", "right", "select", "set", "unnest",
        "update", "using", "values", "where", "with",
    }
)

#: The legacy column, unqualified: a bare ``role`` in a statement that touches ``users`` is
#: taken for it. ``site_role`` is excluded by the lookbehind (``_`` is a word character), and
#: a column qualified by another relation's alias is answered by :func:`_mentions_legacy_column`.
_BARE_LEGACY = re.compile(r"(?<![\w.])role\b", re.IGNORECASE)

#: The elevation column, qualified or not: ``u.site_role`` is as paired as a bare ``site_role``,
#: so a dot must not hide it from the rule.
_ELEVATION = re.compile(r"(?<!\w)site_role\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Violation:
    file: Path
    line: int
    rule: str
    excerpt: str


@dataclass
class ScanOutput:
    violations: list[Violation] = field(default_factory=list)
    pair_readers: set[str] = field(default_factory=set)


def _users_names(text: str) -> set[str]:
    """``users`` plus every alias the statement binds to it."""
    names = {"users"}
    for match in _USERS_RELATION.finditer(text):
        alias = match.group(1)
        if alias and alias.lower() not in _SQL_KEYWORDS:
            names.add(alias)
    return names


def _mentions_legacy_column(text: str, users_names: set[str]) -> bool:
    if _BARE_LEGACY.search(text):
        return True
    return any(
        re.search(rf"\b{re.escape(name)}\.role\b", text, re.IGNORECASE) for name in users_names
    )


def _getattr_role_lines(tree: ast.AST) -> list[int]:
    """Lines where the file asks an arbitrary object for its ``role``."""
    out: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "getattr" or len(node.args) < 2:
            continue
        target = node.args[1]
        if isinstance(target, ast.Constant) and target.value == LEGACY_COLUMN:
            out.append(node.lineno)
    return out


def scan_text(rel: Path, source: str, *, identity_pair_readers: set[str] = frozenset()) -> ScanOutput:
    """Every violation in one file's source. ``rel`` is used for reporting and the allowlist."""
    out = ScanOutput()
    try:
        tree = ast.parse(source, filename=str(rel))
    except SyntaxError:
        return out

    rel_text = rel.as_posix()
    for lineno, text, _interpolated in string_literals(tree):
        if not _USERS_RELATION.search(text):
            continue
        users_names = _users_names(text)
        if not _mentions_legacy_column(text, users_names):
            continue
        excerpt = " ".join(text.split())[:110]
        if not _ELEVATION.search(text):
            out.violations.append(
                Violation(file=rel, line=lineno, rule=RULE_LEGACY_ALONE, excerpt=excerpt)
            )
            continue
        out.pair_readers.add(rel_text)
        if rel_text not in identity_pair_readers:
            out.violations.append(
                Violation(file=rel, line=lineno, rule=RULE_PAIR_OUTSIDE_IDENTITY, excerpt=excerpt)
            )

    for lineno in _getattr_role_lines(tree):
        out.violations.append(
            Violation(file=rel, line=lineno, rule=RULE_CLAIM_READ, excerpt='getattr(..., "role")')
        )
    return out


def _scan_file(root: Path, path: Path, identity_pair_readers: set[str]) -> ScanOutput:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ScanOutput()
    return scan_text(path.relative_to(root), source, identity_pair_readers=identity_pair_readers)


def _pair_readers(config: dict[str, Any]) -> dict[str, str]:
    """``{path: reason}`` from ``identity_pair_readers`` (entries: ``{path, reason}`` or path)."""
    out: dict[str, str] = {}
    entries = config.get("identity_pair_readers")
    if isinstance(entries, (list, tuple)):
        for entry in entries:
            if isinstance(entry, dict):
                path = str(entry.get("path") or "").strip()
                if path:
                    out[path] = str(entry.get("reason") or "").strip()
            elif isinstance(entry, str) and entry.strip():
                out[entry.strip()] = ""
    return out


_FIX_HINTS = {
    RULE_LEGACY_ALONE: (
        f"read `{ELEVATION_COLUMN}` beside it, or drop `{LEGACY_COLUMN}` from the statement — "
        f"elevation is `users.{ELEVATION_COLUMN}`"
    ),
    RULE_PAIR_OUTSIDE_IDENTITY: (
        f"ask the identity resolver instead of the columns: `db.user_site_role(user_id)` / "
        f"`db.user_effective_role(user_id)`; if this really is identity infrastructure, add it "
        f"to `identity_pair_readers` in scripts/checks/config.json with a reason"
    ),
    RULE_CLAIM_READ: (
        "do not read a role off an object — a carried claim cannot elevate; "
        f"resolve it with `db.user_effective_role(user_id)`"
    ),
}


def _print_summary(violations: list[Violation], limit: int) -> None:
    print(f"  legacy-column violations ({len(violations)}):")
    for v in violations[:limit]:
        print(f"    {v.file}:{v.line}  [{v.rule}]")
        print(f"        {v.excerpt}")
        print(f"        fix: {_FIX_HINTS[v.rule]}")
    if len(violations) > limit:
        print(f"    ... and {len(violations) - limit} more")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    print_header(name)
    root = repo_root()
    pair_readers = _pair_readers(config)

    files = candidate_python_files(root, config)
    if not files:
        print_skip(name, "no python files in scope")
        return CheckResult(name=name, ok=True, skipped=True, message="no files in scope")

    violations: list[Violation] = []
    for path in files:
        violations.extend(_scan_file(root, path, set(pair_readers)).violations)

    if not violations:
        print_pass(name)
        return CheckResult(name=name, ok=True)

    limit = int(config.get("summary_limit") or 20)
    print_fail(name, f"{len(violations)} legacy role-column read(s) in {len(files)} file(s) scanned")
    _print_summary(violations, limit)
    return CheckResult(name=name, ok=False, message=f"{len(violations)} legacy role-column read(s)")
