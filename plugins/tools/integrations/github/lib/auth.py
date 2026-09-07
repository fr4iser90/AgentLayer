"""GitHub PAT for coding git network tools (per-user DB secret only)."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from typing import Any

USER_SECRET_KEY = "github_pat"

_GIT_PAT_SUBCOMMAND_RE = re.compile(
    r"\bgit\s+(push|clone|fetch|pull)\b",
    re.IGNORECASE,
)


def git_command_needs_github_pat(command: str) -> bool:
    """True when a shell command runs git network ops that may need HTTPS PAT."""
    return bool(_GIT_PAT_SUBCOMMAND_RE.search((command or "").strip()))


def git_auth_failure_reason(output: str, exit_code: int) -> str | None:
    if exit_code == 0:
        return None
    low = (output or "").lower()
    if any(
        x in low
        for x in (
            "403 forbidden",
            "permission denied",
            "authentication failed",
            "invalid username or password",
            "access denied",
        )
    ):
        return "auth_denied"
    if "could not read username" in low or "terminal prompts disabled" in low:
        return "no_token"
    return "git_failed"


def no_github_pat_payload() -> dict[str, Any]:
    return {
        "ok": False,
        "reason": "no_token",
        "error": (
            f"No GitHub token for this user. Save `{USER_SECRET_KEY}` in "
            "Settings → Connections (never paste tokens into chat for the model to repeat)."
        ),
    }


def cleanup_askpass_paths(paths: list[str]) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def parse_github_pat(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return s
    if isinstance(obj, dict):
        return str(obj.get("token") or obj.get("pat") or "").strip()
    return s


def github_pat_for_user_id(user_id: Any) -> str | None:
    """Explicit user lookup for HTTP handlers (``user.id`` from auth). Not identity-context."""
    from apps.backend.infrastructure.db import db
    import uuid as _uuid

    if user_id is None:
        return None
    try:
        uid = user_id if isinstance(user_id, _uuid.UUID) else _uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        return None
    raw = db.user_secret_get_plaintext(uid, USER_SECRET_KEY)
    if not raw:
        return None
    tok = parse_github_pat(raw)
    return tok or None


def github_pat_for_current_user() -> str | None:
    from apps.backend.domain.shared.identity import get_identity
    from apps.backend.infrastructure.db import db

    _tid, uid = get_identity()
    if uid is None:
        return None
    raw = db.user_secret_get_plaintext(uid, USER_SECRET_KEY)
    if not raw:
        return None
    tok = parse_github_pat(raw)
    return tok or None


def askpass_extra_env(token: str) -> tuple[dict[str, str], list[str]]:
    """
    Return env vars for ``git`` HTTPS auth and paths to delete in ``finally``.

    Uses a short-lived askpass script + token file (mode 0600); token never passed on argv.
    """
    token_file = tempfile.NamedTemporaryFile(
        mode="w",
        prefix="al-git-tok-",
        suffix=".tmp",
        delete=False,
        encoding="utf-8",
    )
    token_file.write(token)
    token_file.close()
    os.chmod(token_file.name, stat.S_IRUSR | stat.S_IWUSR)

    askpass_fd, askpass_path = tempfile.mkstemp(prefix="al-git-ask-", suffix=".sh")
    os.chmod(askpass_path, stat.S_IRUSR | stat.S_IWUSR)
    # Password prompt → PAT; username prompt → GitHub HTTPS convention (never returned to LLM).
    script = (
        "#!/bin/sh\n"
        f"tok='{token_file.name}'\n"
        'case "$1" in\n'
        "  *[Pp]assword*) exec cat \"$tok\" ;;\n"
        "  *) echo x-access-token ;;\n"
        "esac\n"
    )
    os.write(askpass_fd, script.encode("utf-8"))
    os.close(askpass_fd)
    os.chmod(askpass_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

    env = {
        "GIT_ASKPASS": askpass_path,
        "GIT_TERMINAL_PROMPT": "0",
    }
    return env, [token_file.name, askpass_path]


def redact_secrets(text: str, token: str | None) -> str:
    if not text or not token:
        return text
    return text.replace(token, "***")
