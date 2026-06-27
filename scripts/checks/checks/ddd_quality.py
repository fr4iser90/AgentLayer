from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .common import CheckResult, print_header, print_pass, repo_root


_TACTICAL_MODULE_NAMES = {
    "aggregates.py",
    "entities.py",
    "events.py",
    "policies.py",
    "repositories.py",
    "schemas.py",
    "services.py",
    "value_objects.py",
}


@dataclass(frozen=True)
class DddQualityViolation:
    code: str
    file: Path
    reason: str


def _configured_path(root: Path, raw: Any) -> Path:
    return root / str(raw)


def _root_file_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("bounded_context_roots", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        allowed = set(str(item) for item in rule.get("allow_files", []))
        for file_path in sorted(path.glob("*.py")):
            if file_path.name in allowed:
                continue
            violations.append(
                DddQualityViolation(
                    code="DDDQ001",
                    file=file_path,
                    reason=f"{rule.get('name', path.name)} root must contain context folders, not modules",
                )
            )
    return violations


def _package_root_file_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("package_roots", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        allowed_files = set(str(item) for item in rule.get("allow_files", []))
        required_dirs = set(str(item) for item in rule.get("required_dirs", []))
        ignored_dirs = {"__pycache__", *{str(item) for item in rule.get("ignore_dirs", [])}}
        for child in sorted(path.iterdir()):
            if not child.is_dir() or child.name in ignored_dirs:
                continue
            for required_dir in required_dirs:
                if (child / required_dir).is_dir():
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ007",
                        file=child / required_dir,
                        reason=f"{rule.get('name', path.name)} package is missing required folder",
                    )
                )
            for file_path in sorted(child.glob("*.py")):
                if file_path.name in allowed_files:
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ008",
                        file=file_path,
                        reason=f"{rule.get('name', path.name)} package root must contain folders, not controller modules",
                    )
                )
    return violations


def _layer_root_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("layer_roots", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        allowed_dirs = set(str(item) for item in rule.get("allow_dirs", []))
        allowed_files = set(str(item) for item in rule.get("allow_files", []))
        ignored_dirs = {"__pycache__", *{str(item) for item in rule.get("ignore_dirs", [])}}
        for child in sorted(path.iterdir()):
            if child.is_dir():
                if child.name in allowed_dirs or child.name in ignored_dirs:
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ004",
                        file=child,
                        reason=f"{rule.get('name', path.name)} root contains a directory outside the DDD layer roots",
                    )
                )
                continue
            if child.is_file() and child.name not in allowed_files:
                violations.append(
                    DddQualityViolation(
                        code="DDDQ005",
                        file=child,
                        reason=f"{rule.get('name', path.name)} root contains a file outside the DDD layer roots",
                    )
                )
    return violations


def _root_module_limit_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("root_module_limits", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        allowed_files = set(str(item) for item in rule.get("allow_files", []))
        max_files = int(rule.get("max_files", 0))
        direct_modules = [
            file_path
            for file_path in sorted(path.glob("*.py"))
            if file_path.name not in allowed_files
        ]
        if len(direct_modules) <= max_files:
            continue
        for file_path in direct_modules:
            violations.append(
                DddQualityViolation(
                    code="DDDQ010",
                    file=file_path,
                    reason=(
                        f"{rule.get('name', path.name)} root contains too many direct modules "
                        f"({len(direct_modules)} > {max_files}); move adapters into context/technology packages"
                    ),
                )
            )
    return violations


def _forbidden_dir_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("forbidden_dirs", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        names = {str(item) for item in rule.get("names", [])}
        if not names:
            continue
        for child in sorted(path.rglob("*")):
            if not child.is_dir() or child.name not in names:
                continue
            violations.append(
                DddQualityViolation(
                    code="DDDQ011",
                    file=child,
                    reason=f"{rule.get('name', path.name)} contains generated/cache directory: {child.name}",
                )
            )
    return violations


def _missing_context_files(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("required_context_files", []):
        if not isinstance(rule, dict):
            continue
        context_root = _configured_path(root, rule["path"])
        for raw_context in rule.get("contexts", []):
            context = str(raw_context)
            for raw_required in rule.get("required", []):
                required = context_root / context / str(raw_required)
                if required.exists():
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ002",
                        file=required,
                        reason=f"{rule.get('name', context_root.name)} context is missing required DDD/CQRS file",
                    )
                )
    return violations


def _is_placeholder_module(path: Path) -> bool:
    meaningful = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if len(meaningful) <= 1:
        return True
    if len(meaningful) == 2 and meaningful[0] == "from __future__ import annotations":
        return True
    return False


def _placeholder_tactical_files(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for raw_path in config.get("tactical_module_roots", []):
        path = _configured_path(root, raw_path)
        for file_path in sorted(path.rglob("*.py")):
            if file_path.name not in _TACTICAL_MODULE_NAMES:
                continue
            if not _is_placeholder_module(file_path):
                continue
            violations.append(
                DddQualityViolation(
                    code="DDDQ003",
                    file=file_path,
                    reason="tactical DDD module is an empty placeholder; model it or remove it",
                )
            )
    return violations


def _forbidden_term_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("forbidden_terms", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        terms = [str(term).lower() for term in rule.get("terms", []) if str(term).strip()]
        ignored_dirs = {"__pycache__", *{str(item) for item in rule.get("ignore_dirs", [])}}
        if not terms:
            continue
        for file_path in sorted(path.rglob("*.py")):
            if any(part in ignored_dirs for part in file_path.relative_to(path).parts):
                continue
            lowered = file_path.read_text(encoding="utf-8").lower()
            for term in terms:
                if term not in lowered:
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ006",
                        file=file_path,
                        reason=f"{rule.get('name', path.name)} contains forbidden architecture term: {term}",
                    )
                )
                break
    return violations


def _forbidden_module_glob_violations(root: Path, config: dict[str, Any]) -> list[DddQualityViolation]:
    violations: list[DddQualityViolation] = []
    for rule in config.get("forbidden_module_globs", []):
        if not isinstance(rule, dict):
            continue
        path = _configured_path(root, rule["path"])
        ignored_dirs = {"__pycache__", *{str(item) for item in rule.get("ignore_dirs", [])}}
        for pattern in rule.get("patterns", []):
            for file_path in sorted(path.rglob(str(pattern))):
                if any(part in ignored_dirs for part in file_path.relative_to(path).parts):
                    continue
                violations.append(
                    DddQualityViolation(
                        code="DDDQ009",
                        file=file_path,
                        reason=f"{rule.get('name', path.name)} contains a module matching forbidden pattern: {pattern}",
                    )
                )
    return violations


def _large_files(root: Path, config: dict[str, Any]) -> list[tuple[Path, int]]:
    raw_roots = config.get("large_file_roots", [])
    warn_lines = int(config.get("large_file_warn_lines") or 600)
    files: list[tuple[Path, int]] = []
    for raw_path in raw_roots:
        path = _configured_path(root, raw_path)
        for file_path in sorted(path.rglob("*.py")):
            line_count = len(file_path.read_text(encoding="utf-8").splitlines())
            if line_count > warn_lines:
                files.append((file_path, line_count))
    return sorted(files, key=lambda item: item[1], reverse=True)


def _print_violations(root: Path, violations: list[DddQualityViolation]) -> None:
    print(f"[check:ddd_quality] FAILED: {len(violations)} quality violation(s)")
    for violation in violations:
        print()
        print(f"{violation.code} {violation.file.relative_to(root)}")
        print(f"  {violation.reason}")


def _print_large_files(root: Path, large_files: list[tuple[Path, int]], *, limit: int, threshold: int) -> None:
    print(f"[check:ddd_quality] large files over {threshold} lines:")
    for file_path, line_count in large_files[:limit]:
        print(f"  {line_count:4} {file_path.relative_to(root)}")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    root = repo_root()
    print_header(name)

    violations = [
        *_root_file_violations(root, config),
        *_package_root_file_violations(root, config),
        *_layer_root_violations(root, config),
        *_root_module_limit_violations(root, config),
        *_forbidden_dir_violations(root, config),
        *_missing_context_files(root, config),
        *_placeholder_tactical_files(root, config),
        *_forbidden_term_violations(root, config),
        *_forbidden_module_glob_violations(root, config),
    ]
    if violations:
        _print_violations(root, violations)
        return CheckResult(name=name, ok=False, message=f"{len(violations)} quality violation(s)")

    large_files = _large_files(root, config)
    if large_files:
        warn_lines = int(config.get("large_file_warn_lines") or 600)
        summary_limit = int(config.get("large_file_summary_limit") or 10)
        _print_large_files(root, large_files, limit=summary_limit, threshold=warn_lines)
        if bool(config.get("large_file_enforce", False)):
            return CheckResult(
                name=name,
                ok=False,
                message=f"{len(large_files)} file(s) over {warn_lines} lines",
            )

    print_pass(name)
    return CheckResult(name=name, ok=True)
