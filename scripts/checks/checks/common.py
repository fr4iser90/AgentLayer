from __future__ import annotations

import ast
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    skipped: bool = False
    message: str = ""


def docstring_node_ids(tree: ast.AST) -> set[int]:
    """Node ids of docstring constants — prose about a column or table is not a query."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False) is None:
                continue
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def string_literals(tree: ast.AST) -> list[tuple[int, str, bool]]:
    """``(line, text, interpolated)`` for every non-docstring string in the file.

    f-strings contribute their literal text with interpolations blanked to a space;
    ``interpolated`` records that something was blanked out. A JoinedStr is treated as a
    leaf — descending into it would report each literal fragment a second time as an
    uninterpolated string.
    """
    found: list[tuple[int, str, bool]] = []
    docstrings = docstring_node_ids(tree)

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


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def print_header(name: str) -> None:
    print(f"[check:{name}] running")


def print_skip(name: str, message: str) -> None:
    print(f"[check:{name}] skipped - {message}")


def print_fail(name: str, message: str) -> None:
    print(f"[check:{name}] FAILED - {message}")


def print_pass(name: str) -> None:
    print(f"[check:{name}] passed")


def tool_exists(command: Sequence[str]) -> bool:
    if not command:
        return False
    executable = command[0]
    if executable == "python3" and len(command) >= 3 and command[1] == "-m":
        return shutil.which("python3") is not None
    return shutil.which(executable) is not None


def run_command(
    *,
    name: str,
    command: Sequence[str],
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> CheckResult:
    print_header(name)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(command, cwd=cwd or repo_root(), env=merged_env)
    if completed.returncode == 0:
        print_pass(name)
        return CheckResult(name=name, ok=True)
    print_fail(name, f"exit code {completed.returncode}")
    return CheckResult(name=name, ok=False, message=f"exit code {completed.returncode}")


def candidate_python_files(root: Path, config: Mapping[str, object]) -> list[Path]:
    """Resolve the .py files a check should look at, per its ``scope``/``include``/``ignore``.

    ``scope: "all"`` walks the include roots; anything else uses staged+working-tree
    changes, which is what a pre-commit hook wants.
    """
    import fnmatch  # noqa: PLC0415  (kept local so the module import stays cheap)

    scope = str(config.get("scope") or "staged")
    include_roots = [root / str(path) for path in _as_sequence(config.get("include"))] or [root]
    if scope == "all":
        files = [path for include in include_roots for path in include.rglob("*.py")]
    else:
        files = [root / path for path in staged_or_changed_files(root) if path.suffix == ".py"]

    ignore_globs = [str(pattern) for pattern in _as_sequence(config.get("ignore"))]
    out: list[Path] = []
    for file_path in files:
        try:
            rel = file_path.relative_to(root)
        except ValueError:
            continue
        if not file_path.is_file():
            continue
        if not any(file_path.is_relative_to(include) for include in include_roots):
            continue
        if any(fnmatch.fnmatch(str(rel), pattern) for pattern in ignore_globs):
            continue
        out.append(file_path)
    return sorted(set(out))


def _as_sequence(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def staged_or_changed_files(root: Path) -> list[Path]:
    commands = [
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        ["git", "diff", "--name-only", "--diff-filter=ACMR"],
    ]
    paths: list[Path] = []
    seen: set[Path] = set()
    for command in commands:
        res = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
        if res.returncode != 0:
            continue
        for raw in res.stdout.splitlines():
            if not raw.strip():
                continue
            path = Path(raw.strip())
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths
