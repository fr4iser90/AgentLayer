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
