"""Static tenant-scope check: no unscoped SQL against a tenant-scoped table.

A statement that names a tenant-scoped table must either filter on ``tenant_id``
or be marked ``# tenant-scope: site-wide`` on the line above or on its own line.
Anything else is reported.

Detection is verb-anchored (``FROM t`` / ``UPDATE t SET`` / ``DELETE FROM t``)
rather than "the word appears somewhere", so prose that merely mentions a table
name does not register.

Statements built by f-string interpolation are reported separately as
*unresolved*: the tenant filter may well live in the interpolated variable, and
this check cannot see into it. They show up in the report-only baseline but do
not fail a staged run.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .common import (
    CheckResult,
    print_fail,
    print_header,
    print_pass,
    print_skip,
    candidate_python_files,
    repo_root,
)

SITE_WIDE_MARKER = "tenant-scope: site-wide"
TENANT_COLUMN = "tenant_id"


@dataclass(frozen=True, slots=True)
class ScopeViolation:
    file: Path
    line: int
    table: str
    excerpt: str
    unresolved: bool = False


@dataclass
class ScanOutput:
    violations: list[ScopeViolation] = field(default_factory=list)
    unresolved: list[ScopeViolation] = field(default_factory=list)


def _verb_anchored(table: str) -> list[re.Pattern[str]]:
    """Patterns that only match when the table is used as a SQL relation."""
    esc = re.escape(table)
    return [
        re.compile(rf"\b(?:FROM|INTO|JOIN)\s+{esc}\b", re.IGNORECASE),
        re.compile(rf"\bDELETE\s+FROM\s+{esc}\b", re.IGNORECASE),
        re.compile(rf"\bUPDATE\s+{esc}\b", re.IGNORECASE),
    ]


def _docstring_node_ids(tree: ast.AST) -> set[int]:
    """Node ids of docstring constants — prose about a table is not a query."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def _string_literals(tree: ast.AST) -> list[tuple[int, str, bool]]:
    """``(line, text, interpolated)`` for every non-docstring string in the file.

    f-strings contribute their literal text with interpolations blanked to a
    space; ``interpolated`` records that something was blanked out. A JoinedStr
    is treated as a leaf — descending into it would report each literal fragment
    a second time as an uninterpolated string.
    """
    found: list[tuple[int, str, bool]] = []
    docstrings = _docstring_node_ids(tree)

    def visit(node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.JoinedStr):
                parts: list[str] = []
                interpolated = False
                for value in child.values:
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        parts.append(value.value)
                    else:
                        parts.append(" ")
                        interpolated = True
                found.append((child.lineno, "".join(parts), interpolated))
                continue
            if isinstance(child, ast.Constant):
                if isinstance(child.value, str) and id(child) not in docstrings:
                    found.append((child.lineno, child.value, False))
                continue
            visit(child)

    visit(tree)
    return found


#: A literal that stops mid-clause was built by concatenation — the rest of the
#: statement, tenant filter included, lives in a value we cannot see.
_DANGLING_SQL = re.compile(
    r"\b(?:WHERE|AND|OR|SET|FROM|JOIN|INTO|VALUES|ORDER\s+BY|GROUP\s+BY|LIMIT)\s*$",
    re.IGNORECASE,
)


def _mentions_table_as_relation(text: str, table: str) -> bool:
    for pattern in _verb_anchored(table):
        if pattern.search(text):
            # UPDATE only counts when it actually looks like a statement.
            if pattern.pattern.startswith(r"\bUPDATE"):
                if not re.search(r"\b(?:SET|WHERE)\b", text, re.IGNORECASE):
                    continue
            return True
    return False


def _marker_near(lines: list[str], lineno: int) -> bool:
    for candidate in (lineno, lineno - 1):
        if 1 <= candidate <= len(lines) and SITE_WIDE_MARKER in lines[candidate - 1]:
            return True
    return False


def scan_text(rel: Path, source: str, tables: list[str]) -> ScanOutput:
    try:
        tree = ast.parse(source, filename=str(rel))
    except SyntaxError:
        return ScanOutput()

    lines = source.splitlines()
    out = ScanOutput()

    for lineno, text, interpolated in _string_literals(tree):
        if TENANT_COLUMN in text:
            continue
        if _marker_near(lines, lineno):
            continue
        for table in tables:
            if _mentions_table_as_relation(text, table):
                # An f-string with a blanked clause, or a literal cut off at
                # WHERE/SET/AND, hides its filter from this scan.
                opaque = interpolated or bool(_DANGLING_SQL.search(text.strip()))
                violation = ScopeViolation(
                    file=rel,
                    line=lineno,
                    table=table,
                    excerpt=" ".join(text.split())[:110],
                    unresolved=opaque,
                )
                (out.unresolved if opaque else out.violations).append(violation)
                break
    return out


def _scan_file(root: Path, path: Path, tables: list[str]) -> ScanOutput:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ScanOutput()
    return scan_text(path.relative_to(root), source, tables)


def _print_summary(title: str, items: list[ScopeViolation], limit: int) -> None:
    if not items:
        return
    print(f"  {title} ({len(items)}):")
    for violation in items[:limit]:
        print(
            f"    {violation.file}:{violation.line}  [{violation.table}]  "
            f"no {TENANT_COLUMN} filter, no `{SITE_WIDE_MARKER}` marker"
        )
        print(f"        {violation.excerpt}")
    if len(items) > limit:
        print(f"    ... and {len(items) - limit} more")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    print_header(name)
    root = repo_root()
    tables = [str(t).strip() for t in config.get("tenant_scoped_tables", []) if str(t).strip()]
    if not tables:
        print_skip(name, "no tenant_scoped_tables configured")
        return CheckResult(name=name, ok=True, skipped=True, message="no tables configured")

    files = candidate_python_files(root, config)
    if not files:
        print_skip(name, "no python files in scope")
        return CheckResult(name=name, ok=True, skipped=True, message="no files in scope")

    out = ScanOutput()
    for path in files:
        scanned = _scan_file(root, path, tables)
        out.violations.extend(scanned.violations)
        out.unresolved.extend(scanned.unresolved)

    limit = int(config.get("summary_limit") or 20)
    report_only = bool(config.get("report_only"))

    if not out.violations and not out.unresolved:
        print_pass(name)
        return CheckResult(name=name, ok=True)

    if report_only:
        print(f"[check:{name}] report_only - {len(out.violations)} unscoped, {len(out.unresolved)} unresolved")
        _print_summary("unscoped statements", out.violations, limit)
        _print_summary("unresolved (tenant filter may live in an interpolated variable)", out.unresolved, limit)
        return CheckResult(name=name, ok=True)

    if not out.violations:
        print_pass(name)
        return CheckResult(name=name, ok=True)

    print_fail(name, f"{len(out.violations)} unscoped statement(s) on tenant data")
    _print_summary("unscoped statements", out.violations, limit)
    _print_summary("unresolved (informational, not blocking)", out.unresolved, limit)
    print(
        f"  fix: add `{TENANT_COLUMN} = %s` to the statement, or mark the line "
        f"`# {SITE_WIDE_MARKER}` if the surface really spans tenants"
    )
    return CheckResult(name=name, ok=False, message=f"{len(out.violations)} unscoped statement(s)")
