"""Bridge: map workspace env var names → user_secrets service_keys; inject at bash runtime.

Bindings live in ``.agentlayer/env_bindings.json`` (names only — never secret values).
Values are loaded from encrypted ``user_secrets`` only for the duration of a subprocess.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BINDINGS_REL = ".agentlayer/env_bindings.json"
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_BINDINGS = 64


def bindings_path(workspace_root: Path) -> Path:
    return workspace_root / BINDINGS_REL


def load_env_bindings(workspace_root: Path) -> dict[str, str]:
    """Return ``{ ENV_NAME: service_key }`` (empty if missing/invalid)."""
    path = bindings_path(workspace_root)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("invalid env bindings file at %s", path)
        return {}
    if not isinstance(raw, dict):
        return {}
    block = raw.get("bindings") if "bindings" in raw else raw
    if not isinstance(block, dict):
        return {}
    out: dict[str, str] = {}
    for env_name, service_key in block.items():
        en = str(env_name or "").strip()
        sk = str(service_key or "").strip().lower()
        if not en or not sk:
            continue
        if not _ENV_NAME_RE.match(en):
            continue
        if len(out) >= _MAX_BINDINGS:
            break
        out[en] = sk
    return out


def save_env_bindings(workspace_root: Path, bindings: dict[str, str]) -> dict[str, str]:
    """Write bindings file (creates ``.agentlayer/``). Returns normalized map."""
    cleaned: dict[str, str] = {}
    for env_name, service_key in bindings.items():
        en = str(env_name or "").strip()
        sk = str(service_key or "").strip().lower()
        if not en or not sk:
            continue
        if not _ENV_NAME_RE.match(en):
            raise ValueError(f"invalid env name {en!r} (use A-Z, 0-9, _)")
        if len(cleaned) >= _MAX_BINDINGS:
            raise ValueError(f"at most {_MAX_BINDINGS} bindings allowed")
        cleaned[en] = sk
    path = bindings_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": 1,
        "note": (
            "Maps process env names → user_secrets service_key. "
            "Secret values are never stored here; bash injects them at runtime."
        ),
        "bindings": cleaned,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return cleaned


def resolve_bound_secrets(
    workspace_root: Path,
    *,
    user_id: Any | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """
    Load bindings and resolve plaintext secrets for the user.

    Returns ``(env_extra, missing_service_keys, bound_env_names)``.
    """
    bindings = load_env_bindings(workspace_root)
    if not bindings:
        return {}, [], []
    if user_id is None:
        return {}, sorted(set(bindings.values())), sorted(bindings.keys())

    from apps.backend.infrastructure.db import db

    cache: dict[str, str | None] = {}
    for service_key in set(bindings.values()):
        try:
            plain = db.user_secret_get_plaintext(user_id, service_key)
        except Exception:
            logger.debug("secret lookup failed for %s", service_key, exc_info=True)
            plain = None
        cache[service_key] = plain if plain and str(plain).strip() else None

    env_extra: dict[str, str] = {}
    missing: list[str] = []
    for env_name, service_key in bindings.items():
        plain = cache.get(service_key)
        if plain is None:
            missing.append(service_key)
            continue
        env_extra[env_name] = str(plain)
    return env_extra, sorted(set(missing)), sorted(bindings.keys())


def redact_injected_secrets(text: str, injected: dict[str, str]) -> str:
    """Replace injected secret values in command output (longest first)."""
    if not text or not injected:
        return text
    out = text
    for val in sorted({v for v in injected.values() if v and len(v) >= 4}, key=len, reverse=True):
        out = out.replace(val, "***")
    return out


def bindings_status_payload(
    workspace_root: Path,
    *,
    user_id: Any | None,
) -> dict[str, Any]:
    """Status for the agent/UI — never includes secret values."""
    bindings = load_env_bindings(workspace_root)
    present_keys: set[str] = set()
    if user_id is not None:
        try:
            from apps.backend.infrastructure.db import db

            present_keys = set(db.user_secret_list_service_keys(user_id))
        except Exception:
            present_keys = set()
    rows = []
    missing = []
    for env_name, service_key in sorted(bindings.items()):
        ok = service_key in present_keys
        rows.append(
            {
                "env": env_name,
                "service_key": service_key,
                "secret_present": ok,
            }
        )
        if not ok:
            missing.append(service_key)
    return {
        "ok": True,
        "path": BINDINGS_REL,
        "bindings": rows,
        "missing_service_keys": sorted(set(missing)),
        "hint": (
            "bash injects these as process env at runtime (not written to .env). "
            "Use save_user_secret / request_user_secret for missing keys, then re-run."
        ),
    }
