"""Decode ``data:`` image URLs from the triggering user message for HTML-build tools."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_MAX_ASSET_FILES = 5
_MAX_DECODED_BYTES = 400_000
_ALLOWED_IMAGE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml"}
)


def _safe_filename(name: str, idx: int) -> str:
    raw = (name or "").strip() or f"image_{idx}"
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)[:120]
    return s or f"image_{idx}"


def _parse_data_url_image(url: str) -> tuple[str, bytes] | None:
    s = url.strip().replace("\n", "").replace("\r", "")
    if not s.startswith("data:"):
        return None
    try:
        semi = s.lower().index(";base64,")
    except ValueError:
        return None
    mime = s[5:semi].strip().lower()
    if not mime.startswith("image/"):
        return None
    if mime == "image/jpg":
        mime = "image/jpeg"
    b64 = s[semi + 8 :]
    try:
        raw = base64.b64decode(b64, validate=True)
    except Exception:
        return None
    return mime, raw


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
    """Last ``user`` message before the final ``assistant`` (tool-calling) message."""
    if not messages:
        return None
    if messages[-1].get("role") != "assistant":
        return None
    for j in range(len(messages) - 2, -1, -1):
        m = messages[j]
        if m.get("role") == "user":
            return m
    return None


def assets_from_chat_user_images(messages: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """
    Build ``assets`` entries (``name``, ``media_type``, ``data_base64``) from embedded
    ``image_url`` data URLs. Honors optional ``agent_filename`` / ``agentFilename`` on each part
    (set by the agent-ui for original upload names such as ``hero.png``).
    """
    um = triggering_user_message(messages)
    if not um:
        return []
    parts = _user_content_parts(um)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    img_i = 0
    for part in parts:
        if (part.get("type") or "").strip() != "image_url":
            continue
        iu = part.get("image_url")
        if not isinstance(iu, dict):
            continue
        url = iu.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        parsed = _parse_data_url_image(url)
        if not parsed:
            continue
        mime, data = parsed
        if len(data) > _MAX_DECODED_BYTES:
            logger.warning("chat image attachment skipped (too large): %d bytes", len(data))
            continue
        if mime not in _ALLOWED_IMAGE_TYPES:
            logger.warning("chat image attachment skipped (unsupported type): %s", mime)
            continue
        if mime == "image/svg+xml" and len(data) > 50_000:
            logger.warning("chat SVG attachment skipped (too large)")
            continue
        raw_name = part.get("agent_filename") or part.get("agentFilename")
        name_hint = str(raw_name).strip() if isinstance(raw_name, str) else ""
        fname = _safe_filename(name_hint, img_i)
        if "." not in fname:
            suf = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/webp": ".webp",
                "image/gif": ".gif",
                "image/svg+xml": ".svg",
            }.get(mime, ".img")
            fname = fname + suf
        root, ext = os.path.splitext(fname)
        n = 2
        trial = fname
        while trial in seen:
            trial = f"{root}_{n}{ext}"
            n += 1
        fname = trial
        seen.add(fname)
        b64out = base64.standard_b64encode(data).decode("ascii")
        out.append({"name": fname, "media_type": mime, "data_base64": b64out})
        img_i += 1
        if len(out) >= _MAX_ASSET_FILES:
            break
    return out


def merge_chat_images_into_html_build_assets(
    arguments: dict[str, Any],
    messages: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Prepend chat-derived assets; cap total at :data:`_MAX_ASSET_FILES`. Chat images win on order."""
    chat = assets_from_chat_user_images(messages)
    if not chat:
        return arguments
    merged: list[dict[str, Any]] = list(chat)
    raw = arguments.get("assets")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and len(merged) < _MAX_ASSET_FILES:
                merged.append(item)
    out = dict(arguments)
    out["assets"] = merged[:_MAX_ASSET_FILES]
    return out
