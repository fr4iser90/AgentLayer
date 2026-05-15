"""Agent tools for ``kind: pets`` dashboards — list, read, patch pets, notes, album photos."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.domain.identity import get_identity
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import (
    resolve_dashboard_id_for_kind,
    dashboard_rows_for_kind,
)

__version__ = "1.0.0"
TOOL_ID = "pets"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "pets"
TOOL_LABEL = "Pets dashboard"
TOOL_DESCRIPTION = (
    "Read and update pets dashboards (kind pets): hero image, animals table, markdown notes, photo albums. "
    "dashboard_id is optional when the user has exactly one pets board (same rule as other dashboard tools); "
    "if several exist, pass dashboard_id after listing. Prefer [Dashboard context] when present. "
    "Stored dashboard JSON only — no external vet APIs. "
    "Use when the user asks about *their* animals (name, vet, photos) — they may not say the word “pet”."
)
# Router: lowercased substring match (OR). Avoid bare “hund” — it hits “hundert”. Prefer phrases + species words.
TOOL_TRIGGERS = (
    "pet",
    "pets",
    "haustier",
    "haustiere",
    "tier",
    "tiere",
    "tiername",
    "tiernamen",
    "impfung",
    "entwurmung",
    "tierarzt",
    "album",
    "foto",
    "hero",
    "cover",
    # English
    "my pet",
    "my pets",
    "my dog",
    "my cat",
    "my rabbit",
    "pet name",
    "dog name",
    "cat name",
    "our dog",
    "our cat",
    # German — ownership / “whose animal” (no bare “hund”)
    "mein haustier",
    "meine haustiere",
    "mein tier",
    "meine tiere",
    "unser tier",
    "unser haustier",
    "mein hund",
    "meine hunde",
    "unser hund",
    "dein hund",
    "mein welpe",
    "meine katze",
    "meine katzen",
    "unser kater",
    "mein kaninchen",
    "mein meerschweinchen",
    "mein hamster",
    "mein vogel",
    "mein pferd",
    "wie heißt mein",
    "wie heisst mein",
    "wie heißt unser",
    "wie heisst unser",
    "wie heißt dein",
    "gassi",
    "welpe",
    "welp",
    "katz",
    "aquarium",
    "terrarium",
)
TOOL_CAPABILITIES = ("dashboard.pets.read", "dashboard.pets.write")

_MAX_PETS = 100
_MAX_PHOTOS_PER_ALBUM = 200
_MAX_FIELD_LEN = 4000
_MAX_NOTES = 120_000
_MAX_CAPTION = 500
_MAX_HERO_URL = 4096
_MAX_HERO_CAPTION = 2000
_MAX_HERO_HEADLINE = 400


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (tid, uid)


def _ensure_pets(ws: dict[str, Any]) -> str | None:
    if (ws.get("kind") or "").strip() != "pets":
        return "dashboard is not a pets kind"
    return None


def _clip(s: str, max_len: int) -> str:
    t = (s or "").strip()
    if len(t) > max_len:
        return t[:max_len]
    return t


_PET_STRING_FIELDS = ("name", "species", "birthday", "vaccinations", "deworming", "vet")


def pets_dashboards(arguments: dict[str, Any]) -> str:
    """List pets dashboards for the current user."""
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "pets")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


def pets_read(arguments: dict[str, Any]) -> str:
    """Return pets, albums, and notes for one pets dashboard."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    pets = data.get("pets")
    if not isinstance(pets, list):
        pets = []
    albums = data.get("albums")
    if not isinstance(albums, list):
        albums = []
    notes = data.get("notes")
    if not isinstance(notes, str):
        notes = ""
    intro = data.get("albums_intro")
    if not isinstance(intro, str):
        intro = ""
    hero_raw = data.get("hero")
    if not isinstance(hero_raw, dict):
        hero_raw = {}
    hero_out = {
        "url": str(hero_raw.get("url") or "").strip(),
        "caption": str(hero_raw.get("caption") or ""),
        "headline": str(hero_raw.get("headline") or ""),
    }

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "title": ws.get("title") or "",
            "hero": hero_out,
            "pets": pets,
            "albums": albums,
            "notes": notes,
            "albums_intro": intro,
        },
        ensure_ascii=False,
    )


def pets_patch_pet(arguments: dict[str, Any]) -> str:
    """Merge string fields into one pet row (by pet id or zero-based index)."""
    patch = arguments.get("patch")
    if not isinstance(patch, dict) or not patch:
        return _err("patch must be a non-empty object with allowed string fields")

    pet_id = arguments.get("pet_id")
    pet_index = arguments.get("pet_index")

    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    pets_raw = data.get("pets")
    pets: list[dict[str, Any]] = [dict(x) for x in pets_raw] if isinstance(pets_raw, list) else []

    idx: int | None = None
    if pet_id is not None and str(pet_id).strip():
        pid = str(pet_id).strip()
        for i, row in enumerate(pets):
            if str(row.get("id", "")).strip() == pid:
                idx = i
                break
        if idx is None:
            return _err("pet_id not found in pets list")
    elif pet_index is not None:
        try:
            ix = int(pet_index)
        except (TypeError, ValueError):
            return _err("pet_index must be an integer")
        if ix < 0 or ix >= len(pets):
            return _err("pet_index out of range")
        idx = ix
    else:
        return _err("provide pet_id or pet_index")

    row = dict(pets[idx])
    allowed_in_patch = {k: patch[k] for k in _PET_STRING_FIELDS if k in patch}
    if not allowed_in_patch:
        return _err(f"patch must include at least one of: {', '.join(_PET_STRING_FIELDS)}")

    for k, v in allowed_in_patch.items():
        if v is None:
            row[k] = ""
        elif isinstance(v, (str, int, float)):
            row[k] = _clip(str(v), _MAX_FIELD_LEN)
        else:
            return _err(f"invalid type for field {k!r}")

    pets[idx] = row
    data["pets"] = pets

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {"ok": True, "dashboard_id": str(wid), "pet_index": idx, "pet_id": str(row.get("id", ""))},
        ensure_ascii=False,
    )


def pets_add_pet(arguments: dict[str, Any]) -> str:
    """Append a new pet row with optional name."""
    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    pets_raw = data.get("pets")
    pets: list[dict[str, Any]] = [dict(x) for x in pets_raw] if isinstance(pets_raw, list) else []
    if len(pets) >= _MAX_PETS:
        return _err(f"max {_MAX_PETS} pets — remove rows in the UI first")

    name = _clip(str(arguments.get("name") or "Neues Tier"), 200)
    new_row: dict[str, Any] = {
        "id": f"r_{uuid.uuid4().hex[:12]}",
        "name": name,
        "species": "",
        "birthday": "",
        "vaccinations": "",
        "deworming": "",
        "vet": "",
    }
    pets.append(new_row)
    data["pets"] = pets

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "pet_id": new_row["id"],
            "pets_count": len(pets),
        },
        ensure_ascii=False,
    )


def pets_append_photo(arguments: dict[str, Any]) -> str:
    """Append one gallery entry to albums[album_index].photos (url or wsfile:…)."""
    url = _clip(str(arguments.get("url") or ""), 8000)
    if not url:
        return _err("url is required (image URL or wsfile:… reference)")

    try:
        album_index = int(arguments.get("album_index"))
    except (TypeError, ValueError):
        return _err("album_index must be an integer (0 = first album)")

    caption = _clip(str(arguments.get("caption") or ""), _MAX_CAPTION)

    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    albums_raw = data.get("albums")
    if not isinstance(albums_raw, list) or not albums_raw:
        return _err("dashboard has no albums array — add albums in the dashboard UI or data first")

    albums: list[Any] = list(albums_raw)
    if album_index < 0 or album_index >= len(albums):
        return _err("album_index out of range")

    entry = albums[album_index]
    if not isinstance(entry, dict):
        return _err("album entry is not an object")
    album = dict(entry)
    photos_raw = album.get("photos")
    photos: list[dict[str, Any]] = [dict(x) for x in photos_raw] if isinstance(photos_raw, list) else []
    if len(photos) >= _MAX_PHOTOS_PER_ALBUM:
        return _err(f"album already has max {_MAX_PHOTOS_PER_ALBUM} photos")

    photos.append(
        {
            "id": f"r_{uuid.uuid4().hex[:12]}",
            "url": url,
            "caption": caption,
        }
    )
    album["photos"] = photos
    albums[album_index] = album
    data["albums"] = albums

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps(
        {
            "ok": True,
            "dashboard_id": str(wid),
            "album_index": album_index,
            "photos_count": len(photos),
        },
        ensure_ascii=False,
    )


def pets_patch_hero(arguments: dict[str, Any]) -> str:
    """Merge url / caption / headline into data.hero (dashboard hero block)."""
    patch = arguments.get("patch")
    if not isinstance(patch, dict) or not patch:
        return _err("patch must be a non-empty object with optional url, caption, headline")

    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    allowed: dict[str, str] = {}
    if "url" in patch:
        allowed["url"] = _clip(str(patch.get("url") or ""), _MAX_HERO_URL)
    if "caption" in patch:
        allowed["caption"] = _clip(str(patch.get("caption") or ""), _MAX_HERO_CAPTION)
    if "headline" in patch:
        allowed["headline"] = _clip(str(patch.get("headline") or ""), _MAX_HERO_HEADLINE)
    if not allowed:
        return _err("patch must include at least one of url, caption, headline")

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur = data.get("hero")
    if not isinstance(cur, dict):
        cur = {}
    base = {
        "url": str(cur.get("url") or "").strip(),
        "caption": str(cur.get("caption") or ""),
        "headline": str(cur.get("headline") or ""),
    }
    base.update(allowed)
    data["hero"] = base

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps({"ok": True, "dashboard_id": str(wid), "hero": base}, ensure_ascii=False)


def pets_patch_notes(arguments: dict[str, Any]) -> str:
    """Replace or append the markdown notes field (data.notes)."""
    mode = str(arguments.get("mode") or "replace").strip().lower()
    if mode not in ("replace", "append"):
        return _err("mode must be replace or append")

    text = str(arguments.get("text") or "")
    if mode == "replace" and not text.strip():
        return _err("text must be non-empty for mode=replace")

    ident = _identity()
    if ident is None:
        return _err("No user identity — pets tools need an authenticated chat user.")
    tid, uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        uid, tid, kind="pets", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(uid, tid, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    bad = _ensure_pets(ws)
    if bad:
        return _err(bad)

    data = dict(ws.get("data")) if isinstance(ws.get("data"), dict) else {}
    cur = data.get("notes")
    if not isinstance(cur, str):
        cur = ""
    chunk = _clip(text, _MAX_NOTES)
    if mode == "append":
        combined = _clip((cur + ("\n\n" if cur and chunk else "") + chunk).strip(), _MAX_NOTES)
        data["notes"] = combined
    else:
        data["notes"] = chunk

    updated = dashboard_db.dashboard_update(uid, tid, wid, data=data)
    if updated is None:
        return _err("could not update dashboard (viewer role or conflict)")

    return json.dumps({"ok": True, "dashboard_id": str(wid), "notes_chars": len(data["notes"])}, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "pets_dashboards": pets_dashboards,
    "pets_read": pets_read,
    "pets_patch_pet": pets_patch_pet,
    "pets_add_pet": pets_add_pet,
    "pets_append_photo": pets_append_photo,
    "pets_patch_hero": pets_patch_hero,
    "pets_patch_notes": pets_patch_notes,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "pets_dashboards",
            "TOOL_DESCRIPTION": (
                "List pets dashboards the user can open (kind pets). "
                "Call when which pets board is unclear or there is no [Dashboard context] dashboard_id."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_read",
            "TOOL_DESCRIPTION": (
                "Read hero image fields, pets table rows, photo albums, and markdown notes for one pets dashboard. "
                "Omit dashboard_id when the user has exactly one pets board (auto-selected); "
                "if several exist, call pets_dashboards or pass dashboard_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single pets dashboard).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_patch_pet",
            "TOOL_DESCRIPTION": (
                "Update one pet's string fields (name, species, birthday, vaccinations, deworming, vet). "
                "Identify the row with pet_id (row id) or pet_index (0-based). Requires editor/co-owner/owner. "
                "Omit dashboard_id when the user has exactly one pets dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if the user has exactly one pets dashboard.",
                    },
                    "pet_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Row id from pets[].id (preferred when known)",
                    },
                    "pet_index": {
                        "type": "integer",
                        "TOOL_DESCRIPTION": "Zero-based index in pets[] if pet_id unknown",
                    },
                    "patch": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Subset of name, species, birthday, vaccinations, deworming, vet",
                    },
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_add_pet",
            "TOOL_DESCRIPTION": (
                "Add a new empty pet row with optional name (default 'Neues Tier'). "
                "Omit dashboard_id when the user has exactly one pets dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single pets dashboard).",
                    },
                    "name": {"type": "string", "TOOL_DESCRIPTION": "Optional display name for the new pet"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_append_photo",
            "TOOL_DESCRIPTION": (
                "Append one photo entry to albums[album_index].photos with url (or wsfile:…) and optional caption. "
                "album_index 0 = first album in data.albums."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single pets dashboard).",
                    },
                    "album_index": {"type": "integer", "TOOL_DESCRIPTION": "Index into data.albums"},
                    "url": {"type": "string", "TOOL_DESCRIPTION": "Image URL or wsfile:{uuid} from dashboard upload"},
                    "caption": {"type": "string", "TOOL_DESCRIPTION": "Optional caption"},
                },
                "required": ["album_index", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_patch_hero",
            "TOOL_DESCRIPTION": (
                "Update the dashboard hero strip (data.hero): merge url (https or wsfile:…), "
                "caption, and/or headline. Requires editor/co-owner/owner. "
                "Omit dashboard_id when the user has exactly one pets dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single pets dashboard).",
                    },
                    "patch": {
                        "type": "object",
                        "TOOL_DESCRIPTION": "Fields to merge: url, caption, headline (any subset)",
                    },
                },
                "required": ["patch"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pets_patch_notes",
            "TOOL_DESCRIPTION": (
                "Set (mode=replace) or append (mode=append) the markdown notes field. "
                "Omit dashboard_id when the user has exactly one pets dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID; omit if unambiguous (single pets dashboard).",
                    },
                    "mode": {"type": "string", "TOOL_DESCRIPTION": "replace or append"},
                    "text": {"type": "string", "TOOL_DESCRIPTION": "Markdown text"},
                },
                "required": ["mode", "text"],
            },
        },
    },
]
