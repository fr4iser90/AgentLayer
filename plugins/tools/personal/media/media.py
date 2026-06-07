"""Media library tools — list, quota, embed, dashboard queue management."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.data_paths import get_path, set_path, top_level_key
from apps.backend.dashboard.layout_tree import iter_layout_blocks
from apps.backend.dashboard.tool_dashboard_resolve import resolve_dashboard_id
from apps.backend.domain.identity import get_identity
from apps.backend.media import media_db, media_policy

__version__ = "0.1.0"
TOOL_ID = "media"
TOOL_BUCKET = "media"
TOOL_DOMAIN = "media"
TOOL_LABEL = "Media library"
TOOL_DESCRIPTION = (
    "User media library: list uploads and embeds, check storage quota, add allowlisted embed URLs, "
    "HTTPS live streams (internet radio), and manage dashboard media_player queues (enqueue/dequeue/now playing). "
    "Chat audio attachments are auto-ingested. No YouTube download — embed links, streams, and user uploads only. "
    "Requires operator media library enabled."
)
TOOL_TRIGGERS = (
    "media",
    "music",
    "musik",
    "audio",
    "playlist",
    "queue",
    "track",
    "song",
    "lied",
    "lieder",
    "stream",
    "radio",
    "webradio",
    "internetradio",
    "mdr",
    "jump",
    "spotify",
    "youtube",
    "vimeo",
    "mediathek",
    "now playing",
    "warteschlange",
    "mp3",
)
TOOL_CAPABILITIES = ("media.read", "media.write")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "media_list": {"min_role": "user", "capabilities": ("media.read",)},
    "media_quota": {"min_role": "user", "capabilities": ("media.read",)},
    "media_add_embed": {"min_role": "user", "capabilities": ("media.write",)},
    "media_add_stream": {"min_role": "user", "capabilities": ("media.write",)},
    "media_enqueue": {"min_role": "user", "capabilities": ("media.write",)},
    "media_dequeue": {"min_role": "user", "capabilities": ("media.write",)},
    "media_set_now_playing": {"min_role": "user", "capabilities": ("media.write",)},
    "media_delete_item": {"min_role": "user", "capabilities": ("media.write",)},
    "media_update_metadata": {"min_role": "user", "capabilities": ("media.write",)},
    "media_set_license": {"min_role": "user", "capabilities": ("media.write",)},
    "media_share_grant": {"min_role": "user", "capabilities": ("media.write",)},
    "media_list_shares": {"min_role": "user", "capabilities": ("media.read",)},
    "media_revoke_share": {"min_role": "user", "capabilities": ("media.write",)},
}

_MAX_QUEUE_ITEMS = 200
_MAX_LIST = 100


def _err(msg: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": msg, **extra}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (int(tid), uid)


def _media_gate(user_id: uuid.UUID, *, write: bool = False) -> str | None:
    if not media_db.media_tables_exist():
        return _err("media schema not installed (run migrations schema_080)", reason="schema_missing")
    if not media_policy.effective_media_library_enabled(user_id=user_id):
        return _err(
            "media library disabled by operator",
            library_enabled=False,
        )
    if write and not media_policy.effective_media_upload_enabled(user_id=user_id):
        # embed-only writes still allowed when upload disabled
        pass
    return None


def _can_write_dashboard(ws: dict[str, Any]) -> bool:
    role = (ws.get("access_role") or "owner").strip().lower()
    if role == "viewer":
        return False
    if ws.get("access_scope") == "granular":
        return ws.get("granular_can_write") is True
    return role in ("owner", "co_owner", "editor")


def _public_item(row: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": row["id"],
        "source_kind": row["source_kind"],
        "title": row.get("title") or "",
        "artist": row.get("artist") or "",
        "media_ref": f"media:{row['id']}",
    }
    if row.get("source_kind") == "upload":
        out["stream_url"] = f"/v1/media/items/{row['id']}/stream"
    if row.get("source_kind") == "external_link" and row.get("external_url"):
        out["playback_url"] = row["external_url"]
    if row.get("external_url"):
        out["external_url"] = row["external_url"]
    return out


def _read_queue(raw: Any) -> dict[str, Any]:
    if raw and isinstance(raw, dict):
        items = raw.get("items")
        return {
            "now_playing_id": str(raw["now_playing_id"]) if raw.get("now_playing_id") else None,
            "items": list(items) if isinstance(items, list) else [],
            "shuffle": bool(raw.get("shuffle")),
            "repeat": raw.get("repeat") if raw.get("repeat") in ("off", "one", "all") else "off",
        }
    return {"now_playing_id": None, "items": [], "shuffle": False, "repeat": "off"}


def _queue_item_from_media_row(row: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {
        "ref": f"media:{row['id']}",
        "title": row.get("title") or "",
        "artist": row.get("artist") or "",
        "source_kind": row.get("source_kind") or "",
    }
    if row.get("external_url"):
        item["external_url"] = row["external_url"]
    if row.get("source_kind") == "upload":
        item["stream_url"] = f"/v1/media/items/{row['id']}/stream"
    return item


def _resolve_media_dashboard_id(
    uid: uuid.UUID, tid: int, raw_dashboard_id: Any
) -> tuple[uuid.UUID | None, str | None]:
    if raw_dashboard_id is not None and str(raw_dashboard_id).strip():
        return resolve_dashboard_id(uid, tid, raw_dashboard_id)
    rows = dashboard_db.dashboard_list(uid, tid, limit=200)
    if not rows:
        return None, "No dashboards yet — create one in the app first."
    media_rows = [r for r in rows if (r.get("kind") or "").strip() == "media_station"]
    if len(media_rows) == 1:
        rid = media_rows[0].get("id")
        try:
            return (rid if isinstance(rid, uuid.UUID) else uuid.UUID(str(rid))), None
        except (ValueError, TypeError):
            pass
    return resolve_dashboard_id(uid, tid, None)


def _insert_url_item(
    *,
    tid: int,
    uid: uuid.UUID,
    dash_uuid: uuid.UUID | None,
    url: str,
    title: str,
    artist: str,
) -> dict[str, Any]:
    if media_policy.embed_url_allowed(url):
        return media_db.item_insert_embed(
            tenant_id=tid,
            owner_user_id=uid,
            dashboard_id=dash_uuid,
            external_url=url,
            embed_provider=media_policy.embed_provider_for_url(url),
            title=title,
            artist=artist,
        )
    if media_policy.stream_url_allowed(url):
        return media_db.item_insert_external_link(
            tenant_id=tid,
            owner_user_id=uid,
            dashboard_id=dash_uuid,
            external_url=url,
            embed_provider=media_policy.stream_provider_for_url(url),
            title=title,
            artist=artist,
        )
    raise ValueError("URL not allowlisted for embed or HTTPS stream")


def _media_queue_paths(ws: dict[str, Any]) -> list[str]:
    ul = ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else {}
    paths: list[str] = []
    for b in iter_layout_blocks(ul):
        if str(b.get("type") or "").strip().lower() == "media_player":
            props = b.get("props") if isinstance(b.get("props"), dict) else {}
            dp = str(props.get("dataPath") or "media_queue").strip() or "media_queue"
            if dp not in paths:
                paths.append(dp)
    return paths or ["media_queue"]


def _resolve_queue_path(ws: dict[str, Any], queue_path: str | None) -> str | None:
    paths = _media_queue_paths(ws)
    qp = (queue_path or "").strip()
    if qp:
        return qp if qp in paths else None
    return paths[0]


def _save_dashboard_data(
    *,
    uid: uuid.UUID,
    tid: int,
    wid: uuid.UUID,
    ws: dict[str, Any],
    new_data: dict[str, Any],
) -> str | None:
    updated = dashboard_db.dashboard_update(uid, tid, wid, data=new_data)
    if updated is None:
        return "could not update dashboard (viewer or conflict)"
    try:
        from apps.backend.infrastructure.notifications_service import notify_dashboard_agent_update

        notify_dashboard_agent_update(
            tenant_id=tid,
            user_id=uid,
            dashboard_id=wid,
            dashboard_title=str(ws.get("title") or ""),
            patches=[{"path": "(media_queue)", "value": "updated"}],
            ui_layout=ws.get("ui_layout") if isinstance(ws.get("ui_layout"), dict) else None,
        )
    except Exception:
        pass
    return None


def list_items(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    sk = str(arguments.get("source_kind") or "").strip() or None
    if sk and sk not in ("embed", "upload", "external_link", "archive"):
        return _err("invalid source_kind")
    lim = arguments.get("limit")
    try:
        limit = int(lim) if lim is not None else 50
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(limit, _MAX_LIST))
    rows = media_db.item_list_accessible(user_id=uid, tenant_id=tid, source_kind=sk, limit=limit)
    return json.dumps(
        {"ok": True, "items": [_public_item(r) for r in rows], "count": len(rows)},
        ensure_ascii=False,
    )


def quota(arguments: dict[str, Any]) -> str:
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    if not media_db.media_tables_exist():
        return _err("media schema not installed (run migrations schema_080)", reason="schema_missing")
    snap = media_policy.media_quota_snapshot(user_id=uid, tenant_id=tid)
    snap["upload_enabled"] = media_policy.effective_media_upload_enabled(user_id=uid)
    return json.dumps({"ok": True, **snap}, ensure_ascii=False)


def add_embed(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    url = str(arguments.get("external_url") or "").strip()
    if not url:
        return _err("external_url required")
    if not media_policy.embed_url_allowed(url):
        return _err("embed URL not allowed")
    dash_raw = arguments.get("dashboard_id")
    dash_uuid: uuid.UUID | None = None
    if dash_raw:
        try:
            dash_uuid = uuid.UUID(str(dash_raw).strip())
        except ValueError:
            return _err("invalid dashboard_id")
    row = media_db.item_insert_embed(
        tenant_id=tid,
        owner_user_id=uid,
        dashboard_id=dash_uuid,
        external_url=url,
        embed_provider=media_policy.embed_provider_for_url(url),
        title=str(arguments.get("title") or "").strip()[:500],
        artist=str(arguments.get("artist") or "").strip()[:500],
    )
    return json.dumps({"ok": True, "item": _public_item(row)}, ensure_ascii=False)


def add_stream(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    url = str(arguments.get("stream_url") or arguments.get("external_url") or "").strip()
    if not url:
        return _err("stream_url required")
    if not media_policy.stream_url_allowed(url):
        return _err("stream URL not allowed (HTTPS + allowlisted radio/stream host)")
    dash_raw = arguments.get("dashboard_id")
    dash_uuid: uuid.UUID | None = None
    if dash_raw:
        try:
            dash_uuid = uuid.UUID(str(dash_raw).strip())
        except ValueError:
            return _err("invalid dashboard_id")
    row = media_db.item_insert_external_link(
        tenant_id=tid,
        owner_user_id=uid,
        dashboard_id=dash_uuid,
        external_url=url,
        embed_provider=media_policy.stream_provider_for_url(url),
        title=str(arguments.get("title") or "").strip()[:500],
        artist=str(arguments.get("artist") or "").strip()[:500],
    )
    return json.dumps({"ok": True, "item": _public_item(row)}, ensure_ascii=False)


def enqueue(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    wid, res_err = _resolve_media_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write_dashboard(ws):
        return _err("read-only access — cannot update queue")

    qp = _resolve_queue_path(ws, str(arguments.get("queue_path") or "").strip() or None)
    if qp is None:
        return _err("queue_path not found on dashboard (add a media_player block first)")

    media_item_id_raw = arguments.get("media_item_id")
    external_url = str(arguments.get("external_url") or "").strip()
    queue_item: dict[str, Any] | None = None

    if media_item_id_raw:
        try:
            mid = uuid.UUID(str(media_item_id_raw).strip())
        except ValueError:
            return _err("invalid media_item_id")
        row = media_db.item_get_owned(mid, uid, tid)
        if not row:
            return _err("media item not found")
        queue_item = _queue_item_from_media_row(row)
    elif external_url:
        try:
            row = _insert_url_item(
                tid=tid,
                uid=uid,
                dash_uuid=wid,
                url=external_url,
                title=str(arguments.get("title") or "").strip()[:500],
                artist=str(arguments.get("artist") or "").strip()[:500],
            )
        except ValueError as e:
            return _err(str(e))
        queue_item = _queue_item_from_media_row(row)
    else:
        return _err("media_item_id or external_url required")

    data = dict(ws.get("data") or {})
    q = _read_queue(get_path(data, qp))
    if len(q["items"]) >= _MAX_QUEUE_ITEMS:
        return _err(f"queue full (max {_MAX_QUEUE_ITEMS} items)")
    q["items"] = list(q["items"]) + [queue_item]
    play_now = arguments.get("play_now")
    if play_now is True or str(play_now).lower() in ("1", "true", "yes"):
        ref = queue_item.get("ref") or ""
        q["now_playing_id"] = ref.replace("media:", "") if ref.startswith("media:") else ref
    elif not q["now_playing_id"] and q["items"]:
        ref = str(q["items"][0].get("ref") or "")
        q["now_playing_id"] = ref.replace("media:", "") if ref.startswith("media:") else ref or None

    new_data = set_path(data, qp, q)
    if ws.get("access_scope") == "granular":
        allowed = top_level_key(qp)
        keys = {top_level_key(p) for p in _media_queue_paths(ws)}
        if allowed not in keys:
            return _err("granular share cannot write this queue path")

    err = _save_dashboard_data(uid=uid, tid=tid, wid=wid, ws=ws, new_data=new_data)
    if err:
        return _err(err)
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "queue_path": qp,
            "item": queue_item,
            "queue_length": len(q["items"]),
            "now_playing_id": q.get("now_playing_id"),
        },
        ensure_ascii=False,
    )


def dequeue(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    wid, res_err = _resolve_media_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write_dashboard(ws):
        return _err("read-only access — cannot update queue")

    qp = _resolve_queue_path(ws, str(arguments.get("queue_path") or "").strip() or None)
    if qp is None:
        return _err("queue_path not found on dashboard")

    data = dict(ws.get("data") or {})
    q = _read_queue(get_path(data, qp))
    items = list(q["items"])
    if not items:
        return _err("queue is empty")

    idx_raw = arguments.get("index")
    ref_raw = str(arguments.get("media_ref") or arguments.get("ref") or "").strip()
    removed: dict[str, Any] | None = None

    if idx_raw is not None:
        try:
            idx = int(idx_raw)
        except (TypeError, ValueError):
            return _err("invalid index")
        if idx < 0 or idx >= len(items):
            return _err("index out of range")
        removed = items.pop(idx)
    elif ref_raw:
        target = ref_raw if ref_raw.startswith("media:") else f"media:{ref_raw}"
        found = -1
        for i, it in enumerate(items):
            if str(it.get("ref") or "").strip() == target:
                found = i
                break
        if found < 0:
            return _err("item not in queue")
        removed = items.pop(found)
    else:
        return _err("index or media_ref required")

    removed_id = str(removed.get("ref") or "").replace("media:", "") if removed else ""
    if q.get("now_playing_id") and removed_id and str(q["now_playing_id"]) == removed_id:
        q["now_playing_id"] = (
            str(items[0].get("ref") or "").replace("media:", "") if items else None
        )

    q["items"] = items
    new_data = set_path(data, qp, q)
    err = _save_dashboard_data(uid=uid, tid=tid, wid=wid, ws=ws, new_data=new_data)
    if err:
        return _err(err)
    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "queue_path": qp,
            "removed": removed,
            "queue_length": len(items),
        },
        ensure_ascii=False,
    )


def set_now_playing(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    wid, res_err = _resolve_media_dashboard_id(uid, tid, arguments.get("dashboard_id"))
    if wid is None:
        return _err(res_err or "dashboard_id required")
    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if not _can_write_dashboard(ws):
        return _err("read-only access — cannot update queue")

    qp = _resolve_queue_path(ws, str(arguments.get("queue_path") or "").strip() or None)
    if qp is None:
        return _err("queue_path not found on dashboard")

    ref_raw = str(arguments.get("media_ref") or arguments.get("media_item_id") or "").strip()
    if not ref_raw:
        return _err("media_ref or media_item_id required")
    nid = ref_raw.replace("media:", "")

    data = dict(ws.get("data") or {})
    q = _read_queue(get_path(data, qp))
    if q["items"]:
        known = {str(it.get("ref") or "").replace("media:", "") for it in q["items"]}
        if nid not in known:
            return _err("item not in queue — enqueue first")
    q["now_playing_id"] = nid
    new_data = set_path(data, qp, q)
    err = _save_dashboard_data(uid=uid, tid=tid, wid=wid, ws=ws, new_data=new_data)
    if err:
        return _err(err)
    return json.dumps(
        {"ok": True, "dashboard_id": str(wid), "queue_path": qp, "now_playing_id": nid},
        ensure_ascii=False,
    )


def delete_item(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    raw = arguments.get("media_item_id")
    if not raw:
        return _err("media_item_id required")
    try:
        mid = uuid.UUID(str(raw).strip())
    except ValueError:
        return _err("invalid media_item_id")
    row = media_db.item_get_owned(mid, uid, tid)
    if not row:
        return _err("media item not found")
    if row.get("source_kind") != "upload":
        return _err("only upload items can be deleted via this tool (embeds: remove from queue)")
    relpath = media_db.item_soft_delete(mid, uid, tid)
    if relpath is None:
        return _err("could not delete item")
    if relpath:
        from apps.backend.core.config import config
        from apps.backend.dashboard import file_storage

        file_storage.unlink_if_exists(config.media_upload_dir(), relpath)
    return json.dumps({"ok": True, "deleted": str(mid)}, ensure_ascii=False)


def update_metadata(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    raw = arguments.get("media_item_id")
    if not raw:
        return _err("media_item_id required")
    try:
        mid = uuid.UUID(str(raw).strip())
    except ValueError:
        return _err("invalid media_item_id")
    title = arguments.get("title")
    artist = arguments.get("artist")
    if title is None and artist is None:
        return _err("title or artist required")
    sets: list[str] = ["updated_at = now()"]
    params: list[Any] = []
    if title is not None:
        sets.append("title = %s")
        params.append(str(title).strip()[:500])
    if artist is not None:
        sets.append("artist = %s")
        params.append(str(artist).strip()[:500])
    params.extend([mid, tid, uid])
    from apps.backend.infrastructure.db import db

    with db.pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE media_items SET {", ".join(sets)}
                WHERE id = %s AND tenant_id = %s AND owner_user_id = %s AND deleted_at IS NULL
                RETURNING id
                """,
                tuple(params),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        return _err("media item not found")
    updated = media_db.item_get_owned(mid, uid, tid)
    return json.dumps({"ok": True, "item": _public_item(updated or {"id": str(mid)})}, ensure_ascii=False)


def set_license(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    raw = arguments.get("media_item_id")
    if not raw:
        return _err("media_item_id required")
    try:
        mid = uuid.UUID(str(raw).strip())
    except ValueError:
        return _err("invalid media_item_id")
    lic = media_policy.normalize_media_license(arguments.get("license"))
    if not lic:
        return _err("license required (owned, cc-by, cc-by-sa, cc0, other)")
    row = media_db.item_update_license(
        item_id=mid,
        owner_user_id=uid,
        tenant_id=tid,
        license=lic,
        license_note=str(arguments.get("license_note") or "").strip(),
    )
    if not row:
        return _err("upload item not found")
    return json.dumps({"ok": True, "item": _public_item({**row, "access": "owner"})}, ensure_ascii=False)


def share_grant(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    if not media_policy.effective_media_sharing_enabled(user_id=uid):
        return _err("media sharing disabled")
    if not media_db.media_share_tables_exist():
        return _err("media sharing schema not installed")
    raw = arguments.get("media_item_id")
    email = str(arguments.get("email") or "").strip().lower()
    if not raw or not email:
        return _err("media_item_id and email required")
    try:
        mid = uuid.UUID(str(raw).strip())
    except ValueError:
        return _err("invalid media_item_id")
    if arguments.get("license"):
        lic = media_policy.normalize_media_license(arguments.get("license"))
        if lic:
            media_db.item_update_license(
                item_id=mid,
                owner_user_id=uid,
                tenant_id=tid,
                license=lic,
                license_note=str(arguments.get("license_note") or "").strip(),
            )
    from apps.backend.infrastructure.auth import get_user_by_email

    target = get_user_by_email(email)
    if target is None:
        return _err("user not found for this email")
    perm = str(arguments.get("permission") or "play").strip().lower()
    if perm not in ("play", "play_and_download"):
        return _err("permission must be play or play_and_download")
    grant = media_db.share_grant_upsert(
        owner_user_id=uid,
        tenant_id=tid,
        media_item_id=mid,
        viewer_user_id=target.id,
        permission=perm,
    )
    if not grant:
        return _err("could not share (upload + license required, same tenant, not self)")
    return json.dumps({"ok": True, "grant": grant}, ensure_ascii=False)


def list_shares(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    raw = arguments.get("media_item_id")
    mid: uuid.UUID | None = None
    if raw:
        try:
            mid = uuid.UUID(str(raw).strip())
        except ValueError:
            return _err("invalid media_item_id")
    grants = media_db.share_grants_list(owner_user_id=uid, tenant_id=tid, media_item_id=mid)
    return json.dumps({"ok": True, "grants": grants}, ensure_ascii=False)


def revoke_share(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — media tools need an authenticated chat user.")
    tid, uid = ident
    gate = _media_gate(uid)
    if gate:
        return gate
    raw = arguments.get("grant_id")
    if not raw:
        return _err("grant_id required")
    try:
        gid = uuid.UUID(str(raw).strip())
    except ValueError:
        return _err("invalid grant_id")
    if not media_db.share_grant_delete(owner_user_id=uid, tenant_id=tid, grant_id=gid):
        return _err("share grant not found")
    return json.dumps({"ok": True, "removed": True}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "media_list": list_items,
    "media_quota": quota,
    "media_add_embed": add_embed,
    "media_add_stream": add_stream,
    "media_enqueue": enqueue,
    "media_dequeue": dequeue,
    "media_set_now_playing": set_now_playing,
    "media_delete_item": delete_item,
    "media_update_metadata": update_metadata,
    "media_set_license": set_license,
    "media_share_grant": share_grant,
    "media_list_shares": list_shares,
    "media_revoke_share": revoke_share,
}

_TOOLS_COMMON = {
    "dashboard_id": {
        "type": "string",
        "TOOL_DESCRIPTION": "Dashboard UUID. Required for queue tools when several boards exist.",
    },
    "queue_path": {
        "type": "string",
        "TOOL_DESCRIPTION": "dataPath of a media_player block (default: first media_queue on board).",
    },
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "media_list",
            "TOOL_DESCRIPTION": "List media library items (owned + shared with you).",
            "parameters": {
                "type": "object",
                "properties": {
                    "source_kind": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional filter: embed | upload | external_link | archive",
                    },
                    "limit": {"type": "integer", "TOOL_DESCRIPTION": f"Max items (default 50, max {_MAX_LIST})."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_quota",
            "TOOL_DESCRIPTION": "Storage quota: used_bytes, quota_bytes, upload_enabled.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_add_embed",
            "TOOL_DESCRIPTION": "Add allowlisted HTTPS embed (YouTube/Vimeo) to the user's media library.",
            "parameters": {
                "type": "object",
                "properties": {
                    "external_url": {"type": "string", "TOOL_DESCRIPTION": "HTTPS embed or watch URL."},
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                    "dashboard_id": _TOOLS_COMMON["dashboard_id"],
                },
                "required": ["external_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_add_stream",
            "TOOL_DESCRIPTION": (
                "Add HTTPS live audio stream (internet radio, icecast) to library as external_link. "
                "Use media_enqueue with the returned media_item_id to play."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stream_url": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "HTTPS (or HTTP) stream URL, e.g. MDR Jump icecast.",
                    },
                    "title": {"type": "string"},
                    "artist": {"type": "string", "TOOL_DESCRIPTION": "Station or genre label."},
                    "dashboard_id": _TOOLS_COMMON["dashboard_id"],
                },
                "required": ["stream_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_enqueue",
            "TOOL_DESCRIPTION": (
                "Append a library item or new embed/stream URL to a dashboard media_player queue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": _TOOLS_COMMON["dashboard_id"],
                    "queue_path": _TOOLS_COMMON["queue_path"],
                    "media_item_id": {"type": "string", "TOOL_DESCRIPTION": "Existing library item UUID."},
                    "external_url": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Alternative: add allowlisted YouTube/Vimeo embed or HTTPS stream URL then enqueue.",
                    },
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                    "play_now": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "Set as now playing after enqueue (default: first item only).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_dequeue",
            "TOOL_DESCRIPTION": "Remove item from dashboard queue by index or media_ref.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": _TOOLS_COMMON["dashboard_id"],
                    "queue_path": _TOOLS_COMMON["queue_path"],
                    "index": {"type": "integer", "TOOL_DESCRIPTION": "0-based queue index."},
                    "media_ref": {"type": "string", "TOOL_DESCRIPTION": "media:{uuid} or bare UUID."},
                },
                "required": ["dashboard_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_set_now_playing",
            "TOOL_DESCRIPTION": "Set now_playing_id on a dashboard media queue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": _TOOLS_COMMON["dashboard_id"],
                    "queue_path": _TOOLS_COMMON["queue_path"],
                    "media_ref": {"type": "string"},
                    "media_item_id": {"type": "string"},
                },
                "required": ["dashboard_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_delete_item",
            "TOOL_DESCRIPTION": "Soft-delete an owned upload from the media library (not embeds).",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_item_id": {"type": "string", "TOOL_DESCRIPTION": "Upload item UUID."},
                },
                "required": ["media_item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_update_metadata",
            "TOOL_DESCRIPTION": "Update title/artist on an owned media library item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_item_id": {"type": "string"},
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                },
                "required": ["media_item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_set_license",
            "TOOL_DESCRIPTION": "Set license on an owned upload (required before sharing).",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_item_id": {"type": "string"},
                    "license": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "owned | cc-by | cc-by-sa | cc0 | other",
                    },
                    "license_note": {"type": "string"},
                },
                "required": ["media_item_id", "license"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_share_grant",
            "TOOL_DESCRIPTION": "Share an owned upload with another tenant user (license required).",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_item_id": {"type": "string"},
                    "email": {"type": "string"},
                    "permission": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "play (default) or play_and_download",
                    },
                    "license": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional: set license before sharing",
                    },
                    "license_note": {"type": "string"},
                },
                "required": ["media_item_id", "email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_list_shares",
            "TOOL_DESCRIPTION": "List share grants you created (optional filter by media_item_id).",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_item_id": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "media_revoke_share",
            "TOOL_DESCRIPTION": "Revoke a share grant you created.",
            "parameters": {
                "type": "object",
                "properties": {
                    "grant_id": {"type": "string"},
                },
                "required": ["grant_id"],
            },
        },
    },
]
