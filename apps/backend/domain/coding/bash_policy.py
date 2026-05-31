"""Shell policy for ``bash`` / ``workspace_verify`` (blocklist, optional strict allowlist, env scrub)."""

from __future__ import annotations

import os
import re
from typing import Any

_BLOCKED_COMMANDS = frozenset({
    "rm -rf /",
    "rm -rf /*",
    "rm -rf .",
    "rm -rf ./",
    "chmod -R 777 /",
    "dd if=/dev/zero",
    "mkfs",
    "fdisk",
    "parted",
    "iptables",
    "ufw",
})

_BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/",  # rm -rf anything at root
    r"rm\s+-rf\s+\*",  # rm -rf *
    r"rm\s+-rf\s+\.($|\s)",  # wipe workspace cwd
    r"rm\s+-R\s+/",  # rm -R recursive at root
    r"wget\s+.*\|\s*sh",  # wget | sh
    r"wget\s+.*\|\s*bash",
    r"curl\s+.*\|\s*sh",  # curl | sh
    r"curl\s+.*\|\s*bash",
    r":\(\)\s*:",  # fork bomb
    r"fork\(\)",
    r"\$\s*\(\s*\$\s*\)",
    r"dd\s+if=/dev/zero",
    r"dd\s+if=/dev/urandom",
    r">\s*/dev/sd[a-z]",
    r"chmod\s+-R\s+777",
    r"mv\s+/.*\s+/bin",
    r"cp\s+.*\s+/bin",
    r":\|",
    r"git\s+clean\s+-[a-z]*f",  # git clean -fd / -fdx (destructive tree wipe)
]

_BLOCKED_REGEX = [re.compile(p, re.IGNORECASE) for p in _BLOCKED_PATTERNS]

# Used when AGENT_CODING_BASH_STRICT=true (opt-in via env; default off).
_DEFAULT_STRICT_PREFIXES = (
    "git",
    "gh",
    "npm",
    "npx",
    "pnpm",
    "yarn",
    "bun",
    "node",
    "python",
    "python3",
    "pip",
    "pip3",
    "uv",
    "ruff",
    "pytest",
    "make",
    "cmake",
    "cargo",
    "go",
    "docker",
    "docker-compose",
    "compose",
    "ls",
    "cat",
    "head",
    "tail",
    "wc",
    "find",
    "grep",
    "rg",
    "sed",
    "awk",
    "cp",
    "mv",
    "mkdir",
    "rm",
    "touch",
    "chmod",
    "stat",
    "file",
    "which",
    "echo",
    "test",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "sort",
    "uniq",
    "diff",
    "patch",
    "tar",
    "unzip",
    "zip",
    "jq",
    "eslint",
    "tsc",
    "mypy",
    "black",
    "isort",
    "pre-commit",
    "hash",
    "shasum",
    "openssl",
    "printenv",
    "env",
)

_SHELL_META_SPLIT = re.compile(r"\s*(?:;|&&|\|\|)\s*")
_PIPE_SPLIT = re.compile(r"\s*\|\s*")

_ENV_ASSIGN_PREFIX = re.compile(
    r'^([A-Za-z_][A-Za-z0-9_]*)=(?:[^\s"\']|"[^"]*"|\'[^\']*\')\s+'
)

_BARE_SHELL_BUILTINS = frozenset({"cd", "export", "test", "true", "false", "[", "]", "exec"})

_SECRET_ENV_MARKERS = (
    "SECRET",
    "PASSWORD",
    "TOKEN",
    "API_KEY",
    "APIKEY",
    "PRIVATE_KEY",
    "DATABASE_URL",
    "DB_URL",
    "AWS_",
    "GITHUB_PAT",
    "OPENAI",
    "BEARER",
    "CREDENTIAL",
)

_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "PWD",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "USER",
        "LOGNAME",
        "SHELL",
        "TMPDIR",
        "TZ",
        "COLORTERM",
        "NO_COLOR",
        "FORCE_COLOR",
        "CI",
        "DEBIAN_FRONTEND",
    }
)

_SAFE_ENV_PREFIXES = (
    "NODE_",
    "NPM_",
    "npm_",
    "PYTHON",
    "UV_",
    "VIRTUAL_ENV",
    "RUST",
    "CARGO",
    "GOPATH",
    "GOROOT",
    "JAVA_",
    "MAVEN_",
    "GRADLE_",
    "PNPM_",
    "YARN_",
    "BUN_",
    "COMPOSE_",
    "DOCKER_",
)


def resolve_path_under_workspace(root: os.PathLike[str], rel: str | None) -> str:
    """Resolve ``rel`` under workspace ``root``; reject absolute paths and ``..`` escapes."""
    from pathlib import Path

    root_r = Path(root).resolve()
    r = (rel or "").strip().replace("\\", "/")
    if r in ("", "."):
        return str(root_r)
    if r.startswith("/"):
        raise ValueError("workdir must be relative, not absolute")
    target = (root_r / r).resolve()
    try:
        target.relative_to(root_r)
    except ValueError:
        raise ValueError("workdir must stay inside the workspace") from None
    return str(target)


def is_blocked(command: str) -> str | None:
    lower = command.lower().strip()
    for blocked in _BLOCKED_COMMANDS:
        if blocked in lower:
            return f"command blocked: '{blocked}' is not allowed (1)"
    for i, regex in enumerate(_BLOCKED_REGEX):
        if regex.search(lower):
            return f"command blocked: matches dangerous pattern '{_BLOCKED_PATTERNS[i]}' (2)"
    return None


def strict_allowed_prefixes() -> frozenset[str]:
    from apps.backend.core.config import config

    raw = (os.environ.get("AGENT_CODING_BASH_ALLOWED_PREFIXES") or "").strip()
    if raw:
        if raw == "-":
            return frozenset()
        parts = [x.strip().lower() for x in raw.split(",") if x.strip()]
        return frozenset(parts)
    custom = getattr(config, "CODING_BASH_ALLOWED_PREFIXES", None)
    if custom:
        return frozenset(str(x).strip().lower() for x in custom if str(x).strip())
    return frozenset(p.lower() for p in _DEFAULT_STRICT_PREFIXES)


def _strip_env_assignments(segment: str) -> str:
    s = segment.strip()
    while True:
        m = _ENV_ASSIGN_PREFIX.match(s)
        if not m:
            break
        s = s[m.end() :].lstrip()
    return s


def _first_word(segment: str) -> str:
    s = _strip_env_assignments(segment)
    if not s:
        return ""
    if s[0] in "\"'":
        q = s[0]
        end = s.find(q, 1)
        if end > 0:
            return s[1:end]
    m = re.match(r"^(\S+)", s)
    return m.group(1) if m else ""


def _command_segments(command: str) -> list[str]:
    segments: list[str] = []
    for part in _SHELL_META_SPLIT.split(command.strip()):
        if not part.strip():
            continue
        for pipe_part in _PIPE_SPLIT.split(part):
            seg = pipe_part.strip()
            if seg:
                segments.append(seg)
    return segments or [command.strip()]


def strict_mode_reject_reason(command: str) -> str | None:
    """When strict mode is on, only allow segments whose leading command matches configured prefixes."""
    prefixes = strict_allowed_prefixes()
    if not prefixes:
        return "strict bash mode enabled but no allowed prefixes configured"
    segments = _command_segments(command)
    for seg in segments:
        sl = seg.strip().lower()
        if not sl:
            continue
        word = _first_word(seg).lower()
        if word in _BARE_SHELL_BUILTINS:
            continue
        allowed = False
        for prefix in sorted(prefixes, key=len, reverse=True):
            if sl == prefix or sl.startswith(prefix + " ") or sl.startswith(prefix + "\t"):
                allowed = True
                break
            if word and word == prefix:
                allowed = True
                break
        if not allowed:
            hint = ", ".join(sorted(prefixes)[:12])
            return (
                f"command blocked: strict bash mode — segment {seg[:80]!r} not in allowed prefixes "
                f"(e.g. {hint}…). Set AGENT_CODING_BASH_STRICT=false or extend AGENT_CODING_BASH_ALLOWED_PREFIXES."
            )
    return None


def coding_bash_strict_enabled() -> bool:
    from apps.backend.core.config import config

    return bool(getattr(config, "CODING_BASH_STRICT", False))


def unattended_coding_bash_reject_reason(command: str) -> str | None:
    """
    Pre-flight for ``agent_unattended`` ``bash`` calls (same policy as the tool).

    - Always applies the blocklist (``is_blocked``).
    - When ``AGENT_CODING_BASH_STRICT=true``, applies ``strict_mode_reject_reason`` /
      ``AGENT_CODING_BASH_ALLOWED_PREFIXES`` (single allowlist source — not duplicated in agent.py).
    - Otherwise only rejects empty commands and obvious model prose (not a second hardcoded allowlist).
    """
    cmd = (command or "").strip()
    if not cmd:
        return (
            'coding_bash requires {"command": "…"} — empty command is not allowed. '
            'Example: {"command": "git status"} or {"command": "ls -la"}.'
        )
    blocked = is_blocked(cmd)
    if blocked:
        return blocked
    if coding_bash_strict_enabled():
        return strict_mode_reject_reason(cmd)
    sl = cmd.lower()
    if " now i need" in sl or cmd.endswith(":"):
        return f"Invalid shell command (looks like prose, not a command): {cmd[:120]!r}"
    if not _first_word(cmd):
        return f"Invalid shell command (not a one-liner): {cmd[:120]!r}"
    return None


def _env_key_allowed(key: str) -> bool:
    ku = key.upper()
    if ku in _SAFE_ENV_KEYS:
        return True
    for prefix in _SAFE_ENV_PREFIXES:
        if ku.startswith(prefix):
            return True
    for marker in _SECRET_ENV_MARKERS:
        if marker in ku:
            return False
    return True


def subprocess_env_for_coding(
    *,
    home: str,
    cwd: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """
    Build subprocess env: workspace HOME/PWD, optional scrub of operator secrets from ``os.environ``.
    """
    from apps.backend.core.config import config

    out: dict[str, str] = {
        "HOME": home,
        "PWD": cwd,
        "GIT_TERMINAL_PROMPT": "0",
    }
    scrub = bool(getattr(config, "CODING_BASH_ENV_SCRUB", True))
    for key in ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TZ", "TMPDIR"):
        val = os.environ.get(key)
        if val is not None:
            out[key] = val
    if not out.get("PATH"):
        out["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    if scrub:
        for key, val in os.environ.items():
            if key in out:
                continue
            if _env_key_allowed(key):
                out[key] = val
    else:
        out.update({k: v for k, v in os.environ.items() if isinstance(v, str)})
    out["HOME"] = home
    out["PWD"] = cwd
    out["GIT_TERMINAL_PROMPT"] = "0"
    if extra:
        for key, val in extra.items():
            if val is not None:
                out[str(key)] = str(val)
    return out
