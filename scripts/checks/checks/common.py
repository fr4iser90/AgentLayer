from __future__ import annotations

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
