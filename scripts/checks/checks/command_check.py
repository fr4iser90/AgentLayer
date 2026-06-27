from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path
from typing import Any

from .common import CheckResult, print_fail, print_header, print_pass, print_skip, repo_root, run_command, tool_exists


def _provider_config(config: dict[str, Any]) -> dict[str, Any]:
    providers = config.get("providers")
    if not isinstance(providers, dict):
        return config
    env_name = str(config.get("provider_env") or "")
    selected = os.environ.get(env_name) if env_name else None
    provider = selected or str(config.get("default_provider") or "local")
    chosen = providers.get(provider)
    if not isinstance(chosen, dict):
        available = ", ".join(sorted(providers))
        raise ValueError(f"unknown provider {provider!r}; available: {available}")
    merged = {k: v for k, v in config.items() if k != "providers"}
    merged.update(chosen)
    merged["provider"] = provider
    return merged


def _python_module_exists(module: str) -> bool:
    return importlib.util.find_spec(module.replace("-", "_")) is not None


def _run_frontend_i18n_with_nix_fallback(name: str, config: dict[str, Any]) -> CheckResult:
    root = repo_root()
    frontend = root / str(config.get("cwd", "apps/frontend"))
    print_header(name)
    if tool_exists(["npm"]):
        rc = subprocess.run(["npm", "test"], cwd=frontend).returncode
        if rc == 0:
            print_pass(name)
            return CheckResult(name=name, ok=True)
        print_fail(name, "frontend i18n failed (npm in PATH)")
        return CheckResult(name=name, ok=False, message="frontend i18n failed")

    shell_nix = root / "shell.nix"
    if shell_nix.exists() and tool_exists(["nix-shell"]):
        rc = subprocess.run(
            ["nix-shell", str(shell_nix), "--run", "cd apps/frontend && npm test"],
            cwd=root,
        ).returncode
        if rc == 0:
            print_pass(name)
            return CheckResult(name=name, ok=True)
        print_fail(name, "frontend i18n failed inside nix-shell")
        return CheckResult(name=name, ok=False, message="frontend i18n failed inside nix-shell")

    print_skip(name, "npm not in PATH and nix-shell fallback unavailable")
    return CheckResult(name=name, ok=True, skipped=True, message="frontend toolchain unavailable")


def _run_nix_shell_fallback(name: str, command: str) -> CheckResult | None:
    root = repo_root()
    shell_nix = root / "shell.nix"
    if not shell_nix.exists() or not tool_exists(["nix-shell"]):
        return None

    print_header(name)
    rc = subprocess.run(["nix-shell", str(shell_nix), "--run", command], cwd=root).returncode
    if rc == 0:
        print_pass(name)
        return CheckResult(name=name, ok=True)
    print_fail(name, f"nix-shell fallback failed with exit code {rc}")
    return CheckResult(name=name, ok=False, message=f"nix-shell fallback exit code {rc}")


def run(name: str, config: dict[str, Any]) -> CheckResult:
    config = _provider_config(config)
    if config.get("kind") == "frontend_i18n":
        return _run_frontend_i18n_with_nix_fallback(name, config)

    command = config.get("command")
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        raise ValueError(f"check {name!r} must define command as a string list")

    required_tool = config.get("required_tool")
    if isinstance(required_tool, str) and not tool_exists([required_tool]):
        nix_shell_command = config.get("nix_shell_command")
        if isinstance(nix_shell_command, str):
            fallback = _run_nix_shell_fallback(name, nix_shell_command)
            if fallback is not None:
                return fallback
        if config.get("required", True):
            print_fail(name, f"missing required tool: {required_tool}")
            return CheckResult(name=name, ok=False, message=f"missing required tool: {required_tool}")
        print_skip(name, f"missing optional tool: {required_tool}")
        return CheckResult(name=name, ok=True, skipped=True, message=f"missing optional tool: {required_tool}")

    required_module = config.get("required_python_module")
    if isinstance(required_module, str) and not _python_module_exists(required_module):
        nix_shell_command = config.get("nix_shell_command")
        if isinstance(nix_shell_command, str):
            fallback = _run_nix_shell_fallback(name, nix_shell_command)
            if fallback is not None:
                return fallback
        if config.get("required", True):
            print_fail(name, f"missing required Python module: {required_module}")
            return CheckResult(name=name, ok=False, message=f"missing required Python module: {required_module}")
        print_skip(name, f"missing optional Python module: {required_module}")
        return CheckResult(name=name, ok=True, skipped=True, message=f"missing optional Python module: {required_module}")

    cwd = repo_root() / str(config["cwd"]) if config.get("cwd") else repo_root()
    env = {str(k): str(v) for k, v in dict(config.get("env") or {}).items()}
    return run_command(name=name, command=command, cwd=Path(cwd), env=env)
