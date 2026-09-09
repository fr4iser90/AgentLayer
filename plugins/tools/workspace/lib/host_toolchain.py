"""Detect missing host CLIs in the coding-agent container PATH."""

from __future__ import annotations

import errno
import shlex
import shutil
import subprocess
from typing import Any

# (display_name, argv for version probe)
_TOOLCHAIN_PROBES: tuple[tuple[str, list[str]], ...] = (
    ("node", ["node", "--version"]),
    ("npm", ["npm", "--version"]),
    ("npx", ["npx", "--version"]),
    ("python3", ["python3", "--version"]),
    ("pip", ["pip", "--version"]),
    ("git", ["git", "--version"]),
    ("docker", ["docker", "--version"]),
    ("make", ["make", "--version"]),
    ("cargo", ["cargo", "--version"]),
    ("go", ["go", "version"]),
    ("rg", ["rg", "--version"]),
)

_MISSING_HINTS: dict[str, str] = {
    "node": (
        "Node.js is not on PATH in the AgentLayer server container. "
        "Add Node to the runtime Dockerfile (or use workspace execution_mode=client on a host with Node)."
    ),
    "npm": (
        "npm is not on PATH in the AgentLayer server container. "
        "It ships with Node — install Node in the runtime image."
    ),
    "npx": (
        "npx is not on PATH in the AgentLayer server container. "
        "It ships with Node/npm — install Node in the runtime image."
    ),
    "docker": (
        "docker CLI is not available inside the agent container "
        "(no Docker-in-Docker by default)."
    ),
    "cargo": "Rust/cargo is not installed in the agent container.",
    "go": "Go is not installed in the agent container.",
    "rg": "ripgrep (rg) is not installed in the agent container.",
    "chrome": (
        "Playwright Chromium is missing under PLAYWRIGHT_BROWSERS_PATH. "
        "Rebuild/restart agent-layer so the image seed copies, or run: npx playwright install chromium. "
        "See docs/runbooks/playwright.md."
    ),
    "chromium": (
        "Playwright Chromium is missing under PLAYWRIGHT_BROWSERS_PATH. "
        "Rebuild/restart agent-layer so the image seed copies, or run: npx playwright install chromium. "
        "See docs/runbooks/playwright.md."
    ),
}


def first_command_program(command: str) -> str | None:
    """Return the executable name from a bash tool command string."""
    try:
        args = shlex.split(command or "")
    except ValueError:
        return None
    if not args:
        return None
    prog = args[0].strip()
    if not prog or prog.startswith("-"):
        return None
    # basename for paths like /usr/bin/node
    if "/" in prog:
        prog = prog.rsplit("/", 1)[-1]
    return prog or None


def hint_for_missing(program: str | None) -> str:
    if not program:
        return (
            "Executable not found on PATH in the AgentLayer coding container. "
            "Install it in the runtime image, or switch the workspace to execution_mode=client."
        )
    return _MISSING_HINTS.get(
        program,
        (
            f"`{program}` is not on PATH in the AgentLayer coding container. "
            "Install it in the runtime Dockerfile, or use execution_mode=client."
        ),
    )


def missing_executable_payload(command: str, exc: BaseException) -> dict[str, Any]:
    """Structured error when subprocess cannot spawn the program (FileNotFoundError)."""
    prog = first_command_program(command)
    errno_val = getattr(exc, "errno", None)
    is_missing = isinstance(exc, FileNotFoundError) or errno_val == errno.ENOENT
    if not is_missing:
        return {
            "ok": False,
            "error": str(exc),
            "command": command,
        }
    return {
        "ok": False,
        "error": f"executable not found in environment: {prog or str(exc)}",
        "missing_executable": prog,
        "missing_in_environment": True,
        "hint": hint_for_missing(prog),
        "command": command,
        "next_steps": [
            "Call repository.environment to see which CLIs are available in this container.",
            "Do not retry the same missing binary; install it in the image or use another approach.",
        ],
    }


def probe_coding_environment(*, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Probe common coding CLIs; used by repository.environment."""
    present: dict[str, str] = {}
    missing: list[str] = []
    hints: dict[str, str] = {}

    for name, argv in _TOOLCHAIN_PROBES:
        bin_name = argv[0]
        which_path = shutil.which(bin_name, path=env.get("PATH") if env else None)
        if which_path is None:
            missing.append(name)
            hints[name] = hint_for_missing(name)
            continue
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=8,
                env=env,
                check=False,
            )
        except FileNotFoundError:
            missing.append(name)
            hints[name] = hint_for_missing(name)
            continue
        except subprocess.TimeoutExpired:
            missing.append(name)
            hints[name] = f"`{name}` did not respond to a version probe (timeout)."
            continue
        except OSError as e:
            missing.append(name)
            hints[name] = str(e)
            continue
        if result.returncode != 0:
            missing.append(name)
            hints[name] = hint_for_missing(name)
            continue
        ver = (result.stdout or result.stderr or "").strip().split("\n", 1)[0][:160]
        present[name] = ver or which_path

    return {
        "ok": True,
        "scope": "agent_layer_server_container",
        "note": (
            "bash and coding tools run inside the AgentLayer backend container PATH, "
            "not on the user's laptop (unless execution_mode=client)."
        ),
        "present": present,
        "missing": missing,
        "hints": hints,
    }
