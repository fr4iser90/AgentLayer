"""Dashboard image upload infrastructure service as domain attachments (``file:{uuid}`` refs)."""

from __future__ import annotations

import base64
import binascii
import re
import uuid
from typing import Any

import httpx

from apps.backend.infrastructure.platform.config import config
from apps.backend.infrastructure.dashboards import dashboard_persistence as dashboard_db
from apps.backend.infrastructure.dashboards import dashboard_file_storage as file_storage
from apps.backend.infrastructure.dashboards.dashboard_list_ops import append_list_rows
from apps.backend.infrastructure.dashboards.dashboard_upload_bytes import sniff_image_mime
from apps.backend.infrastructure.collections import collections_db_service as col_db
from apps.backend.infrastructure.collections import collections_view_service as domain_svc
from plugins.tools.integrations.http.lib.ssrf import validate_outbound_url
from apps.backend.infrastructure.settings.operator_settings import effective_dashboard_upload_max_bytes

_DATA_URL_RE = re.compile(r"^data:image/[\w+.-]+;base64,", re.I)
_HTTP_TIMEOUT_S = 30.0


def _can_upload_dashboard(ws: dict[str, Any]) -> bool:
    role = (ws.get("access_role") or "").strip().lower()
    if role == "viewer":
        return False
    if ws.get("access_scope") == "granular":
        return ws.get("granular_can_write") is True
    return role in ("owner", "co_owner", "editor")


def decode_image_base64(raw: str) -> tuple[bytes | None, str | None]:
    """Decode base64 or data-URL image. Returns (bytes, error)."""
    s = (raw or "").strip()
    if not s:
        return None, "empty base64"
    if _DATA_URL_RE.match(s):
        s = s.split(",", 1)[-1].strip()
    try:
        data = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as e:
        return None, f"invalid base64: {e}"
    if not data:
        return None, "decoded image is empty"
    return data, None


def fetch_image_bytes(url: str) -> tuple[bytes | None, str | None]:
    """Fetch image from a public URL (SSRF-safe). Returns (bytes, error)."""
    u = (url or "").strip()
    if not u:
        return None, "url required"
    ok, why = validate_outbound_url(u)
    if not ok:
        return None, why

    max_b = effective_dashboard_upload_max_bytes()
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT_S, trust_env=False, follow_redirects=True) as client:
            with client.stream("GET", u, headers={"Accept": "image/*"}) as resp:
                resp.raise_for_status()
                ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ctype and not ctype.startswith("image/"):
                    return None, f"url did not return an image (content-type: {ctype})"
                chunks: list[bytes] = []
                total = 0
                for block in resp.iter_bytes():
                    total += len(block)
                    if total > max_b:
                        return None, f"image too large (max {max_b} bytes)"
                    chunks.append(block)
    except httpx.HTTPError as e:
        return None, f"fetch failed: {e}"

    data = b"".join(chunks)
    if not data:
        return None, "empty response"
    return data, None


def _validate_image_bytes(data: bytes) -> tuple[str | None, str | None]:
    max_b = effective_dashboard_upload_max_bytes()
    if len(data) > max_b:
        return None, f"image too large (max {max_b} bytes)"
    sniff = sniff_image_mime(data[:64])
    if sniff is None:
        return None, "unsupported image type (jpeg, png, gif, webp only)"
    return sniff, None


def store_dashboard_image(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    image_bytes: bytes,
    *,
    original_name: str = "upload.jpg",
) -> dict[str, Any]:
    """Write bytes to disk + user_attachments. Returns {ok, gallery_ref, file, ...}."""
    ws = dashboard_db.dashboard_get(user_id, tenant_id, dashboard_id)
    if ws is None:
        return {"ok": False, "error": "dashboard not found or no access"}
    if not _can_upload_dashboard(ws):
        return {"ok": False, "error": "upload not allowed for this role"}

    mime, err = _validate_image_bytes(image_bytes)
    if err:
        return {"ok": False, "error": err}

    from apps.backend.domain.shares.dashboard_grant import dashboard_tenant_id

    row_tid = dashboard_tenant_id(dashboard_id)
    if row_tid is None:
        return {"ok": False, "error": "dashboard not found"}

    fid = uuid.uuid4()
    relpath = f"{row_tid}/{fid}"
    try:
        file_storage.write_bytes(config.dashboard_upload_dir(), relpath, image_bytes)
    except OSError as e:
        return {"ok": False, "error": f"storage failed: {e}"}

    bindings = domain_svc.resolve_bindings_for_dashboard(ws)
    default_slug = next(iter(bindings.values()), None) if bindings else None
    collection_id = None
    if default_slug:
        col = col_db.collection_get(user_id, default_slug)
        if col:
            collection_id = uuid.UUID(str(col["id"]))

    try:
        att = col_db.attachment_insert(
            tenant_id=row_tid,
            owner_user_id=user_id,
            storage_relpath=relpath,
            content_type=mime or "image/jpeg",
            size_bytes=len(image_bytes),
            original_name=(original_name or "upload.jpg")[:500],
            collection_id=collection_id,
            dashboard_id=dashboard_id,
        )
    except Exception:
        file_storage.unlink_if_exists(config.dashboard_upload_dir(), relpath)
        raise

    gallery_ref = str(att.get("gallery_ref") or f"file:{att['id']}")
    return {
        "ok": True,
        "gallery_ref": gallery_ref,
        "file": {
            "id": att["id"],
            "content_type": att["content_type"],
            "size_bytes": att["size_bytes"],
            "original_name": att["original_name"],
        },
    }


def upload_dashboard_image(
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: uuid.UUID,
    *,
    url: str | None = None,
    base64_data: str | None = None,
    original_name: str = "upload.jpg",
    append_list_path: str | None = None,
    caption: str = "",
) -> dict[str, Any]:
    """
    Upload image and optionally append a gallery row via list_append.
    Provide exactly one of ``url`` or ``base64_data``.
    """
    if url and base64_data:
        return {"ok": False, "error": "pass url or base64_data, not both"}
    if url:
        image_bytes, err = fetch_image_bytes(url)
    elif base64_data:
        image_bytes, err = decode_image_base64(base64_data)
    else:
        return {"ok": False, "error": "url or base64_data required"}

    if err or image_bytes is None:
        return {"ok": False, "error": err or "no image data"}

    stored = store_dashboard_image(
        user_id,
        tenant_id,
        dashboard_id,
        image_bytes,
        original_name=original_name,
    )
    if not stored.get("ok"):
        return stored

    gallery_ref = str(stored.get("gallery_ref") or "")
    out: dict[str, Any] = {
        "ok": True,
        "dashboard_id": str(dashboard_id),
        "gallery_ref": gallery_ref,
        "file": stored.get("file"),
    }

    lp = (append_list_path or "").strip()
    if lp:
        cap = (caption or "")[:500]
        append = append_list_rows(
            user_id,
            tenant_id,
            dashboard_id,
            list_path=lp,
            rows=[{"url": gallery_ref, "caption": cap}],
        )
        if not append.get("ok"):
            out["gallery_append_error"] = str(append.get("error") or "list_append failed")
        else:
            out["appended_to"] = lp
            out["append"] = append

    else:
        out["hint"] = (
            "Set gallery_ref on data via patch_data (e.g. hero.url) or list_append "
            "(e.g. list_path albums.0.photos, rows [{url, caption}])."
        )

    return out
