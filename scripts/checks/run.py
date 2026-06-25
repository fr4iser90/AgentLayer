#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from checks.common import CheckResult, repo_root


def _config_path() -> Path:
    return Path(__file__).resolve().with_name("config.json")


def _load_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _selected_checks(config: dict[str, Any], profile: str, explicit: list[str]) -> list[str]:
    checks = config.get("checks", {})
    if explicit:
        names = explicit
    else:
        profiles = config.get("profiles", {})
        if profile not in profiles:
            available = ", ".join(sorted(profiles))
            raise SystemExit(f"unknown profile {profile!r}; available profiles: {available}")
        names = list(profiles[profile])

    missing = [name for name in names if name not in checks]
    if missing:
        raise SystemExit(f"unknown check(s): {', '.join(missing)}")
    return names


def _skip_set() -> set[str]:
    raw = os.environ.get("SKIP_CHECKS", "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _apply_strict_tools(config: dict[str, Any]) -> None:
    if os.environ.get("CHECK_STRICT_TOOLS") != "1":
        return
    for check in config.get("checks", {}).values():
        if isinstance(check, dict) and "required" in check:
            check["required"] = True


def _run_check(name: str, check_config: dict[str, Any]) -> CheckResult:
    module_name = check_config.get("module")
    if not isinstance(module_name, str):
        raise ValueError(f"check {name!r} has no module")
    module = importlib.import_module(f"checks.{module_name}")
    return module.run(name, check_config)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run modular AgentLayer repository checks.")
    parser.add_argument("--profile", default=os.environ.get("CHECK_PROFILE", "precommit"))
    parser.add_argument("--check", action="append", default=[], help="Run one check by name; repeatable.")
    parser.add_argument("--config", type=Path, default=_config_path())
    parser.add_argument("--list", action="store_true", help="List profiles and checks.")
    args = parser.parse_args()

    root = repo_root()
    os.chdir(root)
    config = _load_config(args.config)
    _apply_strict_tools(config)

    if args.list:
        print("Profiles:")
        for name, checks in sorted(config.get("profiles", {}).items()):
            print(f"  {name}: {', '.join(checks)}")
        print("Checks:")
        for name in sorted(config.get("checks", {})):
            print(f"  {name}")
        return 0

    selected = _selected_checks(config, args.profile, args.check)
    skipped_names = _skip_set()
    if skipped_names:
        selected = [name for name in selected if name not in skipped_names]

    print(f"[checks] profile={args.profile} checks={', '.join(selected) or '(none)'}")
    failures: list[CheckResult] = []
    for name in selected:
        result = _run_check(name, dict(config["checks"][name]))
        if not result.ok:
            failures.append(result)

    if failures:
        print()
        print("[checks] FAILED")
        for failure in failures:
            detail = f" - {failure.message}" if failure.message else ""
            print(f"  {failure.name}{detail}")
        return 1

    print("[checks] all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
