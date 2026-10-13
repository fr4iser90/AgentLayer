"""Workspace-scoped secrets and env→service_key bindings (DB-backed)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from apps.backend.infrastructure.db.db import pool

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SERVICE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,62}$")
_MAX_BINDINGS = 64


def _as_uuid(value: Any) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def user_owns_workspace(user_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM project_workspaces
                WHERE id = %s AND owner_user_id = %s
                """,
                (workspace_id, user_id),
            )
            row = cur.fetchone()
        conn.commit()
    return row is not None


def require_workspace_owner(user_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    if not user_owns_workspace(user_id, workspace_id):
        raise ValueError("workspace not found or not owned by this user")


def user_workspace_secret_upsert(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    service_key: str,
    plaintext: str,
) -> None:
    from apps.backend.infrastructure.identity.crypto_secrets import encrypt_secret

    require_workspace_owner(user_id, workspace_id)
    ct = encrypt_secret(plaintext)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_workspace_secrets
                  (user_id, workspace_id, service_key, ciphertext)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, workspace_id, service_key) DO UPDATE SET
                  ciphertext = EXCLUDED.ciphertext,
                  updated_at = now()
                """,
                (user_id, workspace_id, service_key, ct),
            )
        conn.commit()


def user_workspace_secret_get_plaintext(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    service_key: str,
) -> str | None:
    from apps.backend.infrastructure.identity.crypto_secrets import decrypt_secret

    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ciphertext FROM user_workspace_secrets
                WHERE user_id = %s AND workspace_id = %s AND service_key = %s
                """,
                (user_id, workspace_id, service_key),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return None
    return decrypt_secret(bytes(row[0]))


def user_workspace_secret_delete(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    service_key: str,
) -> bool:
    require_workspace_owner(user_id, workspace_id)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_workspace_secrets
                WHERE user_id = %s AND workspace_id = %s AND service_key = %s
                """,
                (user_id, workspace_id, service_key),
            )
            n = cur.rowcount
        conn.commit()
    return n > 0


def user_workspace_secret_list_service_keys(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> list[str]:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT service_key FROM user_workspace_secrets
                WHERE user_id = %s AND workspace_id = %s
                ORDER BY service_key
                """,
                (user_id, workspace_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return [str(r[0]) for r in rows]


def workspace_env_bindings_load(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> dict[str, str]:
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT env_name, service_key FROM workspace_env_bindings
                WHERE user_id = %s AND workspace_id = %s
                ORDER BY env_name
                """,
                (user_id, workspace_id),
            )
            rows = cur.fetchall()
        conn.commit()
    return {str(r[0]): str(r[1]) for r in rows}


def workspace_env_bindings_replace(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    bindings: dict[str, str],
) -> dict[str, str]:
    """Replace all bindings for this user+workspace with ``bindings`` (validated)."""
    require_workspace_owner(user_id, workspace_id)
    cleaned: dict[str, str] = {}
    for env_name, service_key in bindings.items():
        en = str(env_name or "").strip()
        sk = str(service_key or "").strip().lower()
        if not en or not sk:
            continue
        if not _ENV_NAME_RE.match(en):
            raise ValueError(f"invalid env name {en!r} (use A-Z, 0-9, _)")
        if not _SERVICE_KEY_RE.match(sk):
            raise ValueError(f"invalid service_key {sk!r}")
        if len(cleaned) >= _MAX_BINDINGS:
            raise ValueError(f"at most {_MAX_BINDINGS} bindings allowed")
        cleaned[en] = sk

    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM workspace_env_bindings
                WHERE user_id = %s AND workspace_id = %s
                """,
                (user_id, workspace_id),
            )
            for en, sk in cleaned.items():
                cur.execute(
                    """
                    INSERT INTO workspace_env_bindings
                      (user_id, workspace_id, env_name, service_key)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, workspace_id, en, sk),
                )
        conn.commit()
    return cleaned


def workspace_env_bindings_merge(
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    updates: dict[str, str],
) -> dict[str, str]:
    current = workspace_env_bindings_load(user_id, workspace_id)
    current.update({str(k): str(v) for k, v in updates.items()})
    return workspace_env_bindings_replace(user_id, workspace_id, current)


def resolve_secret_plaintext(
    user_id: uuid.UUID,
    service_key: str,
    *,
    workspace_id: uuid.UUID | None = None,
) -> tuple[str | None, str]:
    """
    Resolve plaintext: workspace secret first, then global user_secrets.

    Returns ``(plaintext_or_None, source)`` where source is
    ``workspace`` | ``global`` | ``missing``.
    """
    from apps.backend.infrastructure.db.user_secrets import user_secret_get_plaintext

    sk = (service_key or "").strip().lower()
    if not sk:
        return None, "missing"
    if workspace_id is not None:
        plain = user_workspace_secret_get_plaintext(user_id, workspace_id, sk)
        if plain and str(plain).strip():
            return str(plain), "workspace"
    plain = user_secret_get_plaintext(user_id, sk)
    if plain and str(plain).strip():
        return str(plain), "global"
    return None, "missing"
