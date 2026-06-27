"""Operator media settings — separate UPDATE to avoid extending the main operator_settings row map."""

from __future__ import annotations

from typing import Any

from apps.backend.infrastructure.db import db
from apps.backend.infrastructure.settings.operator_settings import _invalidate
from apps.backend.infrastructure.media import media_policy


def media_settings_public_fields() -> dict[str, Any]:
    op = media_policy._operator_media_row()
    return {
        "media_library_enabled": bool(op.get("media_library_enabled")),
        "media_user_upload_enabled": bool(op.get("media_user_upload_enabled")),
        "media_sharing_enabled": bool(op.get("media_sharing_enabled")),
        "media_default_user_quota_mb": op.get("media_default_user_quota_mb"),
        "media_upload_max_file_mb": op.get("media_upload_max_file_mb"),
        "media_upload_allowed_mime": (op.get("media_upload_allowed_mime") or "").strip(),
        "media_embed_allowed_hosts": (op.get("media_embed_allowed_hosts") or "").strip(),
        "media_effective_upload_max_bytes": media_policy.effective_media_upload_max_bytes(),
        "media_effective_upload_allowed_mime": sorted(media_policy.effective_media_upload_mime()),
        "media_effective_embed_hosts": sorted(media_policy.effective_media_embed_hosts()),
        "media_effective_default_quota_mb": _effective_default_quota_mb(op),
    }


def _effective_default_quota_mb(op: dict[str, Any]) -> int:
    from apps.backend.infrastructure.platform import config as app_config

    mb = op.get("media_default_user_quota_mb")
    if mb is not None:
        try:
            return max(1, int(mb))
        except (TypeError, ValueError):
            pass
    return app_config.MEDIA_DEFAULT_USER_QUOTA_MB


def apply_media_operator_patch(patch: dict[str, Any]) -> None:
    keys = (
        "media_library_enabled",
        "media_user_upload_enabled",
        "media_sharing_enabled",
        "media_default_user_quota_mb",
        "media_upload_max_file_mb",
        "media_upload_allowed_mime",
        "media_embed_allowed_hosts",
    )
    if not any(k in patch for k in keys):
        return

    cur = media_policy._operator_media_row()
    out = dict(cur)

    if "media_library_enabled" in patch:
        out["media_library_enabled"] = bool(patch["media_library_enabled"])
    if "media_user_upload_enabled" in patch:
        out["media_user_upload_enabled"] = bool(patch["media_user_upload_enabled"])
    if "media_sharing_enabled" in patch:
        out["media_sharing_enabled"] = bool(patch["media_sharing_enabled"])
    if "media_default_user_quota_mb" in patch:
        v = patch["media_default_user_quota_mb"]
        if v is None:
            out["media_default_user_quota_mb"] = None
        else:
            try:
                mb = int(v)
                out["media_default_user_quota_mb"] = mb if mb > 0 else None
            except (TypeError, ValueError):
                out["media_default_user_quota_mb"] = None
    if "media_upload_max_file_mb" in patch:
        v = patch["media_upload_max_file_mb"]
        if v is None:
            out["media_upload_max_file_mb"] = None
        else:
            try:
                mb = int(v)
                out["media_upload_max_file_mb"] = mb if mb > 0 else None
            except (TypeError, ValueError):
                out["media_upload_max_file_mb"] = None
    if "media_upload_allowed_mime" in patch:
        v = patch["media_upload_allowed_mime"]
        out["media_upload_allowed_mime"] = None if v is None else (str(v).strip() or None)
    if "media_embed_allowed_hosts" in patch:
        v = patch["media_embed_allowed_hosts"]
        out["media_embed_allowed_hosts"] = None if v is None else (str(v).strip() or None)

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO operator_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
            cur.execute(
                """
                UPDATE operator_settings SET
                  media_library_enabled = %s,
                  media_user_upload_enabled = %s,
                  media_sharing_enabled = %s,
                  media_default_user_quota_mb = %s,
                  media_upload_max_file_mb = %s,
                  media_upload_allowed_mime = %s,
                  media_embed_allowed_hosts = %s,
                  updated_at = now()
                WHERE id = 1
                """,
                (
                    bool(out.get("media_library_enabled")),
                    bool(out.get("media_user_upload_enabled")),
                    bool(out.get("media_sharing_enabled")),
                    out.get("media_default_user_quota_mb"),
                    out.get("media_upload_max_file_mb"),
                    out.get("media_upload_allowed_mime"),
                    out.get("media_embed_allowed_hosts"),
                ),
            )
        conn.commit()
    _invalidate()
