"""Ingest chat audio attachments (data URLs) into the user media library."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from typing import Any

from apps.backend.core.config import config
from apps.backend.dashboard import file_storage
from apps.backend.media import media_db, media_policy
from apps.backend.media.upload_bytes import sniff_media_mime

logger = logging.getLogger(__name__)

_MAX_DECODED_BYTES = 52_428_800  # 50 MiB cap for chat ingest
_DATA_URL_RE = re.compile(r"^data:([^;,]+)?(?:;[^;,=]+=[^;,=]+)*;base64,", re.IGNORECASE)


def _user_content_parts(user_msg: dict[str, Any]) -> list[dict[str, Any]]:
    c = user_msg.get("content")
    if isinstance(c, list):
        return [p for p in c if isinstance(p, dict)]
    if isinstance(c, str):
        t = c.strip()
        if t.startswith("["):
            try:
                p = json.loads(c)
                if isinstance(p, list):
                    return [x for x in p if isinstance(x, dict)]
            except json.JSONDecodeError:
                pass
    return []


def triggering_user_message(messages: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not messages:
        return None
    for msg in reversed(messages):
        if (msg.get("role") or "").strip().lower() == "user":
            return msg
    return None


def _parse_data_url_audio(url: str) -> tuple[str, bytes] | None:
    s = url.strip().replace("\n", "").replace("\r", "")
    if not s.startswith("data:"):
        return None
    m = _DATA_URL_RE.match(s)
    if not m:
        return None
    mime = (m.group(1) or "application/octet-stream").strip().lower()
    if not mime.startswith("audio/") and mime not in ("application/octet-stream",):
        return None
    b64 = s[m.end() :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return None
    return mime, raw


def _safe_filename(name: str, idx: int) -> str:
    raw = (name or "").strip() or f"audio_{idx}"
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)[:120]
    return s or f"audio_{idx}"


def ingest_chat_audio_attachments(
    messages: list[dict[str, Any]] | None,
    *,
    tenant_id: int,
    user_id: uuid.UUID,
) -> list[dict[str, Any]]:
    """Upload ``agent_audio`` parts from the latest user message into ``media_items``."""
    if not media_db.media_tables_exist():
        return []
    if not media_policy.effective_media_library_enabled(user_id=user_id):
        return []
    if not media_policy.effective_media_upload_enabled(user_id=user_id):
        return []

    um = triggering_user_message(messages)
    if not um:
        return []

    parts = _user_content_parts(um)
    ingested: list[dict[str, Any]] = []
    idx = 0
    for part in parts:
        if (part.get("type") or "").strip() != "agent_audio":
            continue
        au = part.get("audio_url")
        if not isinstance(au, dict):
            continue
        url = au.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        parsed = _parse_data_url_audio(url)
        if not parsed:
            continue
        _declared_mime, data = parsed
        if len(data) > _MAX_DECODED_BYTES:
            logger.warning("chat audio attachment skipped (too large): %d bytes", len(data))
            continue
        max_b = media_policy.effective_media_upload_max_bytes()
        if len(data) > max_b:
            logger.warning("chat audio exceeds media upload max: %d", len(data))
            continue
        sniff = sniff_media_mime(data[:64])
        allowed = media_policy.effective_media_upload_mime()
        if sniff is None or sniff not in allowed:
            logger.warning("chat audio unsupported sniff: %s", sniff)
            continue
        used = media_db.user_upload_bytes_used(user_id=user_id, tenant_id=tenant_id)
        quota = media_policy.effective_media_quota_bytes(user_id=user_id)
        if used + len(data) > quota:
            logger.warning("chat audio skipped: quota exceeded")
            continue

        raw_name = part.get("agent_filename") or part.get("agentFilename")
        name_hint = str(raw_name).strip() if isinstance(raw_name, str) else ""
        fname = _safe_filename(name_hint, idx)
        if "." not in fname:
            ext = {
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/flac": ".flac",
                "audio/ogg": ".ogg",
                "audio/wav": ".wav",
            }.get(sniff, ".audio")
            fname += ext

        fid = uuid.uuid4()
        relpath = f"{tenant_id}/{fid}"
        try:
            file_storage.write_bytes(config.media_upload_dir(), relpath, data)
            row = media_db.item_insert_upload(
                tenant_id=tenant_id,
                owner_user_id=user_id,
                dashboard_id=None,
                storage_relpath=relpath,
                content_type=sniff,
                size_bytes=len(data),
                original_name=fname[:500],
                title=os.path.splitext(fname)[0][:500],
                artist="",
            )
        except Exception:
            file_storage.unlink_if_exists(config.media_upload_dir(), relpath)
            logger.exception("chat audio ingest failed for %s", fname)
            continue

        ingested.append(
            {
                "media_item_id": row["id"],
                "media_ref": f"media:{row['id']}",
                "title": row.get("title") or fname,
                "original_name": fname,
                "content_type": sniff,
                "size_bytes": len(data),
            }
        )
        idx += 1

    return ingested


def format_ingested_audio_system_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lines = [
        "Chat audio attachments were saved to the user's media library (use media_enqueue to play):"
    ]
    for it in items:
        lines.append(
            f"- {it.get('title') or it.get('original_name')}: media_item_id={it.get('media_item_id')} "
            f"({it.get('media_ref')})"
        )
    return "\n".join(lines)
