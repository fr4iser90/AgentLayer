"""Bridge: map workspace env var names → user_secrets service_keys; inject at bash runtime.

Bindings live in Postgres (``workspace_env_bindings``) — names only, never secret values.
Values come from ``user_workspace_secrets`` first, then global ``user_secrets``.

Legacy file ``.agentlayer/env_bindings.json`` is imported once into the DB if present.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Legacy on-disk map (migrated into DB on first use).
BINDINGS_REL = ".agentlayer/env_bindings.json"
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MAX_BINDINGS = 64


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _parse_bindings_dict(raw: Any) -> dict[str, str]:
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


def _load_legacy_file_bindings(workspace_root: Path) -> dict[str, str]:
    path = workspace_root / BINDINGS_REL
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        logger.warning("invalid legacy env bindings file at %s", path)
        return {}
    return _parse_bindings_dict(raw)


def _maybe_migrate_file_to_db(
    workspace_root: Path,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> dict[str, str]:
    """If DB empty and legacy file exists, import once and rename the file."""
    from apps.backend.infrastructure.db import workspace_secrets as wsdb

    current = wsdb.workspace_env_bindings_load(user_id, workspace_id)
    if current:
        return current
    legacy = _load_legacy_file_bindings(workspace_root)
    if not legacy:
        return {}
    try:
        saved = wsdb.workspace_env_bindings_replace(user_id, workspace_id, legacy)
    except Exception:
        logger.exception("failed migrating legacy env_bindings.json to DB")
        return legacy
    path = workspace_root / BINDINGS_REL
    try:
        path.rename(path.with_suffix(path.suffix + ".migrated"))
    except OSError:
        logger.debug("could not rename legacy bindings file", exc_info=True)
    logger.info(
        "migrated %d env bindings from %s into DB for workspace %s",
        len(saved),
        path,
        workspace_id,
    )
    return saved


def load_env_bindings(
    workspace_root: Path | None = None,
    *,
    user_id: Any | None = None,
    workspace_id: Any | None = None,
) -> dict[str, str]:
    """Return ``{ ENV_NAME: service_key }`` from DB (optionally migrating legacy file)."""
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    if uid is None or wid is None:
        if workspace_root is not None:
            return _load_legacy_file_bindings(workspace_root)
        return {}
    from apps.backend.infrastructure.db import workspace_secrets as wsdb

    if workspace_root is not None:
        bindings = _maybe_migrate_file_to_db(workspace_root, user_id=uid, workspace_id=wid)
    else:
        bindings = wsdb.workspace_env_bindings_load(uid, wid)
    if bindings:
        return bindings
    # Heal: workspace secrets exist but bindings were never set (pre-auto-bind installs).
    return _seed_bindings_from_workspace_secrets(uid, wid)


def _seed_bindings_from_workspace_secrets(
    user_id: Any,
    workspace_id: Any,
) -> dict[str, str]:
    """If bindings are empty, derive ENV←service_key from existing workspace secrets."""
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    if uid is None or wid is None:
        return {}
    from apps.backend.infrastructure.db import workspace_secrets as wsdb

    try:
        keys = wsdb.user_workspace_secret_list_service_keys(uid, wid)
    except Exception:
        logger.debug("could not list workspace secrets for binding seed", exc_info=True)
        return {}
    if not keys:
        return {}
    seed: dict[str, str] = {}
    for sk in keys:
        en = service_key_to_default_env_name(sk)
        if en:
            seed[en] = sk
    if not seed:
        return {}
    try:
        saved = wsdb.workspace_env_bindings_replace(uid, wid, seed)
        logger.info(
            "seeded %d env bindings from workspace secrets for workspace %s",
            len(saved),
            wid,
        )
        return saved
    except Exception:
        logger.exception("failed seeding env bindings from workspace secrets")
        return seed



def save_env_bindings(
    workspace_root: Path | None = None,
    bindings: dict[str, str] | None = None,
    *,
    user_id: Any | None = None,
    workspace_id: Any | None = None,
) -> dict[str, str]:
    """Persist bindings in DB. ``workspace_root`` kept for call-site compat (unused)."""
    _ = workspace_root
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    if uid is None or wid is None:
        raise ValueError("user_id and workspace_id are required to save env bindings")
    from apps.backend.infrastructure.db import workspace_secrets as wsdb

    return wsdb.workspace_env_bindings_replace(uid, wid, dict(bindings or {}))


def service_key_to_default_env_name(service_key: str) -> str | None:
    """Derive ``FOO_BAR`` from service_key ``foo_bar`` / ``foo-bar`` / ``foo.bar``."""
    sk = str(service_key or "").strip().lower()
    if not sk:
        return None
    raw = re.sub(r"[.\-]+", "_", sk).upper()
    if not _ENV_NAME_RE.match(raw):
        return None
    return raw


def ensure_env_binding_for_secret(
    *,
    user_id: Any,
    workspace_id: Any,
    service_key: str,
    env_name: str | None = None,
) -> dict[str, Any]:
    """
    Merge one env→service_key binding so bash can inject this secret.

    Called automatically from save_user_secret / HTTP upsert for workspace secrets.
    """
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    sk = str(service_key or "").strip().lower()
    if uid is None or wid is None or not sk:
        return {"bound": False, "reason": "missing user_id, workspace_id, or service_key"}
    en = str(env_name or "").strip() or service_key_to_default_env_name(sk)
    if not en or not _ENV_NAME_RE.match(en):
        return {"bound": False, "reason": "invalid or underivable env name", "service_key": sk}
    from apps.backend.infrastructure.db import workspace_secrets as wsdb

    try:
        merged = wsdb.workspace_env_bindings_merge(uid, wid, {en: sk})
    except ValueError as e:
        return {"bound": False, "reason": str(e), "service_key": sk, "env": en}
    except Exception:
        logger.exception("failed auto-binding %s → %s for workspace %s", en, sk, wid)
        return {"bound": False, "reason": "binding merge failed", "service_key": sk, "env": en}
    return {
        "bound": True,
        "env": en,
        "service_key": sk,
        "bindings_count": len(merged),
    }


def resolve_bound_secrets(
    workspace_root: Path | None,
    *,
    user_id: Any | None,
    workspace_id: Any | None = None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """
    Load bindings and resolve plaintext secrets for the user.

    Workspace-scoped secrets win over global ``user_secrets``.

    Returns ``(env_extra, missing_service_keys, bound_env_names)``.
    """
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    bindings = load_env_bindings(workspace_root, user_id=uid, workspace_id=wid)
    if not bindings:
        return {}, [], []
    if uid is None:
        return {}, sorted(set(bindings.values())), sorted(bindings.keys())

    from apps.backend.infrastructure.db.workspace_secrets import resolve_secret_plaintext

    env_extra: dict[str, str] = {}
    missing: list[str] = []
    for env_name, service_key in bindings.items():
        plain, _src = resolve_secret_plaintext(uid, service_key, workspace_id=wid)
        if plain is None:
            missing.append(service_key)
            continue
        env_extra[env_name] = plain
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
    workspace_root: Path | None = None,
    *,
    user_id: Any | None,
    workspace_id: Any | None = None,
) -> dict[str, Any]:
    """Status for the agent/UI — never includes secret values."""
    uid = _as_uuid(user_id)
    wid = _as_uuid(workspace_id)
    bindings = load_env_bindings(workspace_root, user_id=uid, workspace_id=wid)

    present_global: set[str] = set()
    present_ws: set[str] = set()
    if uid is not None:
        try:
            from apps.backend.infrastructure.db import db
            from apps.backend.infrastructure.db import workspace_secrets as wsdb

            present_global = set(db.user_secret_list_service_keys(uid))
            if wid is not None:
                present_ws = set(wsdb.user_workspace_secret_list_service_keys(uid, wid))
        except Exception:
            present_global = set()
            present_ws = set()

    rows = []
    missing = []
    for env_name, service_key in sorted(bindings.items()):
        in_ws = service_key in present_ws
        in_global = service_key in present_global
        ok = in_ws or in_global
        source = "workspace" if in_ws else ("global" if in_global else "missing")
        rows.append(
            {
                "env": env_name,
                "service_key": service_key,
                "secret_present": ok,
                "secret_source": source,
            }
        )
        if not ok:
            missing.append(service_key)
    return {
        "ok": True,
        "storage": "database",
        "workspace_id": str(wid) if wid else None,
        "legacy_file": BINDINGS_REL,
        "bindings": rows,
        "missing_service_keys": sorted(set(missing)),
        "hint": (
            "Bindings are stored in Postgres for this workspace (not in a repo file). "
            "bash injects values at runtime: workspace secret first, then global user_secrets. "
            "Use save_user_secret with scope=workspace (default when a project is bound) "
            "or request_user_secret for missing keys."
        ),
    }
