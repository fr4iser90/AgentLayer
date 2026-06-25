from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .common import CheckResult, print_fail, print_header, print_pass, print_skip, repo_root, staged_or_changed_files


@dataclass(frozen=True)
class LayerRule:
    name: str
    path: Path
    forbidden_imports: tuple[str, ...]


@dataclass(frozen=True)
class Violation:
    code: str
    file: Path
    line: int
    layer: str
    reason: str
    import_name: str


def _module_name_for_path(root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(root).with_suffix("")
    return ".".join(rel.parts)


def _absolute_import_name(
    *,
    node: ast.ImportFrom,
    current_module: str,
    current_package: str,
) -> str:
    if node.level == 0:
        return node.module or ""
    package_parts = current_package.split(".") if current_package else []
    keep = max(0, len(package_parts) - node.level + 1)
    base = ".".join(package_parts[:keep])
    if node.module:
        return f"{base}.{node.module}" if base else node.module
    return base


def _imports_from_tree(tree: ast.AST, current_module: str) -> Iterable[tuple[int, str]]:
    current_package = current_module.rsplit(".", 1)[0] if "." in current_module else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            import_name = _absolute_import_name(
                node=node,
                current_module=current_module,
                current_package=current_package,
            )
            if import_name:
                yield node.lineno, import_name


def _load_rules(root: Path, config: dict[str, Any]) -> list[LayerRule]:
    rules: list[LayerRule] = []
    for raw in config.get("rules", []):
        if not isinstance(raw, dict):
            continue
        name = str(raw["name"])
        path = root / str(raw["path"])
        forbidden = tuple(str(item) for item in raw.get("forbidden_imports", []))
        rules.append(LayerRule(name=name, path=path, forbidden_imports=forbidden))
    return rules


def _candidate_files(root: Path, config: dict[str, Any]) -> list[Path]:
    scope = str(config.get("scope") or "staged")
    include_roots = [root / str(path) for path in config.get("include", ["apps/backend"])]
    if scope == "all":
        files = [path for include in include_roots for path in include.rglob("*.py")]
    else:
        changed = staged_or_changed_files(root)
        files = [root / path for path in changed if path.suffix == ".py"]

    ignore_globs = [str(pattern) for pattern in config.get("ignore", [])]
    out: list[Path] = []
    for file_path in files:
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            continue
        if not file_path.exists() or not file_path.is_file():
            continue
        if not any(file_path.is_relative_to(include) for include in include_roots):
            continue
        if any(rel.match(pattern) for pattern in ignore_globs):
            continue
        out.append(file_path)
    return sorted(set(out))


def _violations_for_file(root: Path, file_path: Path, rules: list[LayerRule]) -> list[Violation]:
    matched_rules = [rule for rule in rules if file_path.is_relative_to(rule.path)]
    if not matched_rules:
        return []

    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError as exc:
        return [
            Violation(
                code="DDD000",
                file=file_path.relative_to(root),
                line=exc.lineno or 1,
                layer="syntax",
                reason="file could not be parsed",
                import_name=str(exc),
            )
        ]

    current_module = _module_name_for_path(root, file_path)
    violations: list[Violation] = []
    for line, import_name in _imports_from_tree(tree, current_module):
        for rule in matched_rules:
            for forbidden in rule.forbidden_imports:
                if import_name == forbidden or import_name.startswith(f"{forbidden}."):
                    violations.append(
                        Violation(
                            code="DDD001",
                            file=file_path.relative_to(root),
                            line=line,
                            layer=rule.name,
                            reason=f"{rule.name} layer must not import {forbidden}",
                            import_name=import_name,
                        )
                    )
    return violations


def _print_violations(violations: list[Violation]) -> None:
    print(f"[check:ddd_layers] FAILED: {len(violations)} layer violation(s)")
    for violation in violations:
        print()
        print(f"{violation.code} {violation.file}:{violation.line}")
        print(f"  {violation.reason}")
        print(f"  found: {violation.import_name}")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    root = repo_root()
    print_header(name)
    rules = _load_rules(root, config)
    if not rules:
        print_skip(name, "no layer rules configured")
        return CheckResult(name=name, ok=True, skipped=True, message="no layer rules configured")

    files = _candidate_files(root, config)
    if not files:
        print_skip(name, "no matching Python files in scope")
        return CheckResult(name=name, ok=True, skipped=True, message="no matching Python files in scope")

    violations = [violation for file_path in files for violation in _violations_for_file(root, file_path, rules)]
    if violations:
        _print_violations(violations)
        return CheckResult(name=name, ok=False, message=f"{len(violations)} layer violation(s)")

    print_pass(name)
    return CheckResult(name=name, ok=True)
