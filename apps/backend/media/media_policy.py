"""Effective media feature flags and quotas (operator_settings + users + env)."""

from __future__ import annotations

import os
import uuid
from typing import Any

from apps.backend.core import config as app_config
from apps.backend.infrastructure.db import db


def _env_bool_override(key: str) -> bool | None:
    raw = (os.environ.get(key) or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _operator_media_row() -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "media_library_enabled": False,
        "media_user_upload_enabled": False,
        "media_sharing_enabled": False,
        "media_default_user_quota_mb": None,
        "media_upload_max_file_mb": None,
        "media_upload_allowed_mime": None,
        "media_embed_allowed_hosts": None,
    }
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT media_library_enabled, media_user_upload_enabled,
                           media_sharing_enabled, media_default_user_quota_mb,
                           media_upload_max_file_mb, media_upload_allowed_mime,
                           media_embed_allowed_hosts
                    FROM operator_settings WHERE id = 1
                    """
                )
                row = cur.fetchone()
    except Exception:
        return defaults
    if not row:
        return defaults
    return {
        "media_library_enabled": bool(row[0]) if row[0] is not None else False,
        "media_user_upload_enabled": bool(row[1]) if row[1] is not None else False,
        "media_sharing_enabled": bool(row[2]) if row[2] is not None else False,
        "media_default_user_quota_mb": row[3],
        "media_upload_max_file_mb": row[4],
        "media_upload_allowed_mime": row[5],
        "media_embed_allowed_hosts": row[6],
    }


def _user_media_row(user_id: uuid.UUID) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "media_enabled": None,
        "media_storage_quota_mb": None,
        "media_upload_enabled": None,
        "media_sharing_enabled": None,
    }
    try:
        with db.pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT media_enabled, media_storage_quota_mb,
                           media_upload_enabled, media_sharing_enabled
                    FROM users WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
    except Exception:
        return defaults
    if not row:
        return defaults
    return {
        "media_enabled": row[0],
        "media_storage_quota_mb": row[1],
        "media_upload_enabled": row[2],
        "media_sharing_enabled": row[3],
    }


def _inherit_bool(user_val: Any, operator_val: bool) -> bool:
    if user_val is None:
        return bool(operator_val)
    return bool(user_val)


def effective_media_library_enabled(*, user_id: uuid.UUID | None = None) -> bool:
    env = _env_bool_override("AGENT_MEDIA_LIBRARY_ENABLED")
    op = _operator_media_row()
    base = bool(op.get("media_library_enabled"))
    if env is not None:
        base = env
    if user_id is None:
        return base
    user = _user_media_row(user_id)
    return _inherit_bool(user.get("media_enabled"), base)


def effective_media_upload_enabled(*, user_id: uuid.UUID) -> bool:
    if not effective_media_library_enabled(user_id=user_id):
        return False
    env = _env_bool_override("AGENT_MEDIA_USER_UPLOAD_ENABLED")
    op = _operator_media_row()
    op_upload = bool(op.get("media_user_upload_enabled"))
    if env is not None:
        op_upload = env
    user = _user_media_row(user_id)
    return _inherit_bool(user.get("media_upload_enabled"), op_upload)


def effective_media_sharing_enabled(*, user_id: uuid.UUID) -> bool:
    if not effective_media_library_enabled(user_id=user_id):
        return False
    env = _env_bool_override("AGENT_MEDIA_SHARING_ENABLED")
    op = _operator_media_row()
    op_share = bool(op.get("media_sharing_enabled"))
    if env is not None:
        op_share = env
    user = _user_media_row(user_id)
    return _inherit_bool(user.get("media_sharing_enabled"), op_share)


VALID_MEDIA_LICENSES = frozenset({"owned", "cc-by", "cc-by-sa", "cc0", "other"})


def normalize_media_license(raw: Any) -> str | None:
    s = (str(raw or "").strip().lower())
    return s if s in VALID_MEDIA_LICENSES else None


def item_is_shareable(row: dict[str, Any]) -> bool:
    return (
        row.get("source_kind") == "upload"
        and bool(normalize_media_license(row.get("license")))
    )


def effective_media_quota_bytes(*, user_id: uuid.UUID) -> int:
    op = _operator_media_row()
    user = _user_media_row(user_id)
    mb = user.get("media_storage_quota_mb")
    if mb is None:
        mb = op.get("media_default_user_quota_mb")
    if mb is None:
        mb = app_config.MEDIA_DEFAULT_USER_QUOTA_MB
    try:
        n = int(mb)
    except (TypeError, ValueError):
        n = app_config.MEDIA_DEFAULT_USER_QUOTA_MB
    return max(1, n) * 1024 * 1024


def effective_media_upload_max_bytes() -> int:
    op = _operator_media_row()
    v = op.get("media_upload_max_file_mb")
    if v is not None:
        try:
            mb = int(v)
            if mb > 0:
                return mb * 1024 * 1024
        except (TypeError, ValueError):
            pass
    return app_config.MEDIA_UPLOAD_MAX_FILE_MB * 1024 * 1024


def effective_media_upload_mime() -> frozenset[str]:
    op = _operator_media_row()
    raw = op.get("media_upload_allowed_mime")
    if isinstance(raw, str) and raw.strip():
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return app_config.media_upload_env_allowed_mime()


def effective_media_stream_hosts() -> frozenset[str]:
    op = _operator_media_row()
    raw = op.get("media_stream_allowed_hosts")
    if isinstance(raw, str) and raw.strip():
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return app_config.media_stream_env_allowed_hosts()


def effective_media_embed_hosts() -> frozenset[str]:
    op = _operator_media_row()
    raw = op.get("media_embed_allowed_hosts")
    if isinstance(raw, str) and raw.strip():
        return frozenset(x.strip().lower() for x in raw.split(",") if x.strip())
    return app_config.media_embed_env_allowed_hosts()


def _hostname_allowed(hostname: str, allowed: frozenset[str]) -> bool:
    h = hostname.lower()
    for a in allowed:
        al = a.lower()
        if h == al or h.endswith(f".{al}"):
            return True
    return False


def embed_url_allowed(raw: str) -> bool:
    s = (raw or "").strip()
    if not s:
        return False
    from urllib.parse import urlparse

    try:
        u = urlparse(s)
    except ValueError:
        return False
    if u.scheme != "https":
        return False
    host = (u.hostname or "").lower()
    if not host:
        return False
    return _hostname_allowed(host, effective_media_embed_hosts())


def stream_url_allowed(raw: str) -> bool:
    """HTTPS live stream / direct audio URL (internet radio, icecast, …)."""
    s = (raw or "").strip()
    if not s:
        return False
    from urllib.parse import urlparse

    try:
        u = urlparse(s)
    except ValueError:
        return False
    if u.scheme not in ("https", "http"):
        return False
    host = (u.hostname or "").lower()
    if not host:
        return False
    if _hostname_allowed(host, effective_media_stream_hosts()):
        return True
    # Also allow direct audio paths on embed hosts (e.g. CDN mp3)
    path = (u.path or "").lower()
    if path.endswith((".mp3", ".aac", ".ogg", ".opus", ".m4a", ".flac", ".wav")):
        return _hostname_allowed(host, effective_media_embed_hosts() | effective_media_stream_hosts())
    return False


def stream_provider_for_url(raw: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(raw).hostname or "").lower()
    if "mdr" in host:
        return "mdr"
    if "streamtheworld" in host:
        return "streamtheworld"
    if "addradio" in host:
        return "addradio"
    return host.split(".")[-2] if "." in host else "stream"


def embed_provider_for_url(raw: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(raw).hostname or "").lower()
    if "youtube" in host or "youtu.be" in raw.lower():
        return "youtube"
    if "vimeo" in host:
        return "vimeo"
    return host.split(".")[-2] if "." in host else "embed"


def media_quota_snapshot(*, user_id: uuid.UUID, tenant_id: int) -> dict[str, Any]:
    from apps.backend.media import media_db

    used = media_db.user_upload_bytes_used(user_id=user_id, tenant_id=tenant_id)
    quota = effective_media_quota_bytes(user_id=user_id)
    return {
        "library_enabled": effective_media_library_enabled(user_id=user_id),
        "upload_enabled": effective_media_upload_enabled(user_id=user_id),
        "sharing_enabled": effective_media_sharing_enabled(user_id=user_id),
        "used_bytes": used,
        "quota_bytes": quota,
        "remaining_bytes": max(0, quota - used),
    }
