"""Shallow git clone with retries (network / HTTP2 flakiness)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CLONE_ATTEMPTS = 3
DEFAULT_CLONE_TIMEOUT_S = 180
_RETRY_BACKOFF_S = (1.0, 2.5, 5.0)

# curl/git transport flakes seen in production (e.g. curl 56 mid-pack).
_TRANSIENT_MARKERS = (
    "connection reset",
    "recv failure",
    "early eof",
    "rpc failed",
    "curl 56",
    "curl 28",
    "curl 35",
    "curl 52",
    "curl 55",
    "curl 92",
    "transfer closed",
    "unexpected disconnect",
    "fetch-pack",
    "http2",
    "timed out",
    "timeout",
    "temporarily unavailable",
    "tls",
    "ssl",
    "unable to access",
    "could not resolve host",
    "network is unreachable",
    "connection timed out",
)

_BRANCH_MISSING_MARKERS = (
    "remote branch",
    "not found in upstream",
    "did not match any",
    "pathspec",
)


class GitCloneError(Exception):
    """Raised when all clone attempts fail."""

    def __init__(self, message: str, *, attempts: int = 0) -> None:
        super().__init__(message)
        self.attempts = attempts


def _clean_dest(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)


def is_transient_git_error(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _TRANSIENT_MARKERS)


def is_branch_missing_error(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _BRANCH_MISSING_MARKERS)


def _clone_env(*, force_http1: bool) -> dict[str, str]:
    env = os.environ.copy()
    # Abort hung transfers sooner than a silent multi-minute stall.
    env.setdefault("GIT_HTTP_LOW_SPEED_LIMIT", "1000")
    env.setdefault("GIT_HTTP_LOW_SPEED_TIME", "60")
    if force_http1:
        # Avoid HTTP/2 multiplex resets that often surface as curl 56 / early EOF.
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.version"
        env["GIT_CONFIG_VALUE_0"] = "HTTP/1.1"
    return env


def _run_clone(
    git_url: str,
    dest: Path,
    *,
    branch: str | None,
    depth: int,
    timeout_s: int,
    force_http1: bool,
) -> tuple[int, str]:
    cmd: list[str] = ["git", "clone", "--depth", str(max(1, depth))]
    if branch:
        cmd.extend(["--branch", branch])
    # Single-branch shallow clone; skip checkout of other refs.
    cmd.append("--single-branch")
    cmd.extend([git_url, str(dest)])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            env=_clone_env(force_http1=force_http1),
        )
    except subprocess.TimeoutExpired as e:
        out = ((e.stderr or b"") + (e.stdout or b"")).decode("utf-8", errors="replace")
        return -1, (out.strip() or f"git clone timed out after {timeout_s}s")
    except OSError as e:
        return -1, str(e)
    err = ((proc.stderr or "") + ("\n" + proc.stdout if proc.stdout else "")).strip()
    return int(proc.returncode), err


def clone_shallow_repo(
    git_url: str,
    dest: Path | str,
    *,
    branch: str | None = "main",
    depth: int = 1,
    attempts: int = DEFAULT_CLONE_ATTEMPTS,
    timeout_s: int = DEFAULT_CLONE_TIMEOUT_S,
) -> None:
    """
    Shallow-clone ``git_url`` into ``dest``.

    Retries transient network/HTTP failures. After the first failure, forces
    ``http.version=HTTP/1.1``. If ``branch`` is missing on the remote, retries
    without ``--branch`` (remote HEAD).
    """
    url = (git_url or "").strip()
    if not url:
        raise GitCloneError("git_url required")
    if not shutil.which("git"):
        raise GitCloneError("git binary not found in PATH")

    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)

    max_attempts = max(1, int(attempts))
    br = (branch or "").strip() or None
    last_err = "git clone failed"
    tried_without_branch = False

    for i in range(max_attempts):
        force_http1 = i > 0
        _clean_dest(target)
        # git clone creates dest; leave parent only
        code, err = _run_clone(
            url,
            target,
            branch=br,
            depth=depth,
            timeout_s=timeout_s,
            force_http1=force_http1,
        )
        if code == 0 and (target / ".git").exists():
            if i > 0:
                logger.info(
                    "git clone succeeded on attempt %s/%s http1=%s branch=%r",
                    i + 1,
                    max_attempts,
                    force_http1,
                    br,
                )
            return

        last_err = err or f"git clone failed (exit {code})"
        _clean_dest(target)
        logger.warning(
            "git clone attempt %s/%s failed http1=%s branch=%r: %s",
            i + 1,
            max_attempts,
            force_http1,
            br,
            last_err[:400],
        )

        if br and is_branch_missing_error(last_err) and not tried_without_branch:
            logger.info("git clone: branch %r missing; retrying remote HEAD", br)
            br = None
            tried_without_branch = True
            continue

        if i + 1 >= max_attempts:
            break
        if not is_transient_git_error(last_err) and not force_http1:
            # Still try once with HTTP/1.1 before giving up on "non-transient" labels.
            pass
        delay = _RETRY_BACKOFF_S[min(i, len(_RETRY_BACKOFF_S) - 1)]
        time.sleep(delay)

    raise GitCloneError(f"Git clone failed: {last_err[:800]}", attempts=max_attempts)
