"""Upload pending dashboard storage images during an agent tool loop."""

from __future__ import annotations

import json
import uuid
from typing import Any

from apps.backend.application.agent_runtime.dependencies import (
    dashboard_db,
    iter_layout_blocks,
    upload_dashboard_image,
)


def dashboard_id_from_tool_result(result: str | None) -> str | None:
    try:
        data = json.loads(result or "")
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    direct = data.get("dashboard_id") or data.get("id")
    if direct:
        s = str(direct).strip()
        if s:
            return s
    dash = data.get("dashboard")
    if isinstance(dash, dict):
        did = dash.get("id") or dash.get("dashboard_id")
        if did:
            s = str(did).strip()
            if s:
                return s
    return None


def storage_images_from_body(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for idx, item in enumerate(raw[:8]):
        if not isinstance(item, dict):
            continue
        data_url = str(item.get("data_url") or item.get("dataUrl") or "").strip()
        if not data_url.startswith("data:image/"):
            continue
        name = str(item.get("name") or f"image_{idx + 1}.jpg").strip()[:200]
        out.append({"name": name or f"image_{idx + 1}.jpg", "data_url": data_url})
    return out


def first_gallery_data_path(ui_layout: Any) -> str | None:
    if not isinstance(ui_layout, dict):
        return None
    for block in iter_layout_blocks(ui_layout):
        if not isinstance(block, dict):
            continue
        btype = str(block.get("type") or "").strip().lower()
        if btype not in ("gallery", "photo_album", "image_gallery"):
            continue
        props = block.get("props") if isinstance(block.get("props"), dict) else {}
        path = str(props.get("dataPath") or props.get("data_path") or "").strip()
        if path:
            return path
    return None


def storage_upload_prompt(images: list[dict[str, str]]) -> str:
    names = ", ".join(img["name"] for img in images[:5])
    more = f" (+{len(images) - 5} more)" if len(images) > 5 else ""
    return (
        f"{len(images)} image upload(s) are attached server-side for storage: {names}{more}.\n"
        "Do not analyze image pixels unless the user explicitly asks for visual analysis and a VLM is available. "
        "For dashboard/photo-album/gallery requests, create or select the dashboard and a gallery/photo-album block. "
        "Do not call artifact_get for these images and do not invent artifact ids like photo_1/photo_2; "
        "the backend will upload the attached image bytes into the gallery after the dashboard/gallery exists."
    )


def upload_pending_storage_images(
    *,
    tool_context: dict[str, Any],
    user_id: uuid.UUID,
    tenant_id: int,
    dashboard_id: str,
) -> dict[str, Any]:
    pending = tool_context.get("agent_storage_images_pending")
    if not isinstance(pending, list) or not pending:
        return {"ok": True, "uploaded": 0, "pending": 0}
    try:
        dash_uuid = uuid.UUID(str(dashboard_id))
    except (TypeError, ValueError):
        return {"ok": False, "error": "invalid dashboard_id", "uploaded": 0, "pending": len(pending)}

    dashboard = dashboard_db.dashboard_get(user_id, tenant_id, dash_uuid)
    if not dashboard:
        return {"ok": False, "error": "dashboard not found", "uploaded": 0, "pending": len(pending)}
    list_path = first_gallery_data_path(dashboard.get("ui_layout"))
    if not list_path:
        return {"ok": False, "error": "no gallery block yet", "uploaded": 0, "pending": len(pending)}

    uploaded = 0
    errors: list[str] = []
    remaining: list[dict[str, str]] = []
    for image in pending:
        if not isinstance(image, dict):
            continue
        name = str(image.get("name") or "upload.jpg")
        data_url = str(image.get("data_url") or "")
        result = upload_dashboard_image(
            user_id,
            tenant_id,
            dash_uuid,
            base64_data=data_url,
            original_name=name,
            append_list_path=list_path,
            caption=name,
        )
        if result.get("ok") and not result.get("gallery_append_error"):
            uploaded += 1
        else:
            remaining.append(image)
            errors.append(str(result.get("gallery_append_error") or result.get("error") or "upload failed"))
    tool_context["agent_storage_images_pending"] = remaining
    prev = int(tool_context.get("agent_storage_images_uploaded") or 0)
    tool_context["agent_storage_images_uploaded"] = prev + uploaded
    return {
        "ok": not remaining,
        "uploaded": uploaded,
        "pending": len(remaining),
        "dashboard_id": str(dash_uuid),
        "list_path": list_path,
        **({"errors": errors[:3]} if errors else {}),
    }
