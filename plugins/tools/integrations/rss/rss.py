"""RSS connector — fetch feeds, LLM-summarize; persist via dashboard or return to agent."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import feedparser
import httpx

from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import resolve_dashboard_id
from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import get_identity, reset_identity, set_identity
from apps.backend.infrastructure.conversations_db import conversation_append_message, conversation_create

__version__ = "1.0.0"
TOOL_ID = "rss"
TOOL_BUCKET = "network"
TOOL_DOMAIN = "rss"
TOOL_LABEL = "RSS"
TOOL_DESCRIPTION = (
    "Fetch RSS/Atom feeds and summarize with the chat model. "
    "Feed URLs from dashboard.data.feeds (dashboard.read) or feed_urls argument. "
    "Persist with persist_dashboard=true (default) or return markdown for dashboard.patch_data."
)
# Router phrases: co-located rss.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_CAPABILITIES = ("rss.summarize",)
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "summarize": {"min_role": "user", "capabilities": ("rss.summarize",)},
}

_MAX_FEEDS = 200
_MAX_ITEMS_PER_FEED = 15
_HTTP_TIMEOUT_S = 25.0
_MAX_HISTORY = 200


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)


def _identity() -> tuple[int, uuid.UUID] | None:
    tid, uid = get_identity()
    if uid is None:
        return None
    return (int(tid), uid)


def _coerce_feed_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    raw = data.get("feeds")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for r in raw[:_MAX_FEEDS]:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "enabled": bool(r.get("enabled", True)),
                "title": str(r.get("title") or "").strip(),
                "url": url,
                "tags": str(r.get("tags") or "").strip(),
            }
        )
    return rows


def _feeds_from_arguments(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    raw_urls = arguments.get("feed_urls")
    if isinstance(raw_urls, list) and raw_urls:
        out: list[dict[str, Any]] = []
        for u in raw_urls[:_MAX_FEEDS]:
            url = str(u or "").strip()
            if url:
                out.append({"enabled": True, "title": "", "url": url, "tags": ""})
        return out
    return []


async def _summarize_one(*, title: str, url: str, content: str, language: str) -> str:
    lang = (language or "de").strip().lower()
    if lang not in ("de", "en"):
        lang = "de"
    prompt = (
        "You are a technical news editor.\n"
        f"Summarize the article in {('German' if lang == 'de' else 'English')}.\n"
        "Rules: max 3 short sentences, no preamble, no bullet list unless necessary.\n\n"
        f"Title: {title}\n"
        f"URL: {url}\n\n"
        f"Content:\n{content[:12000]}\n"
    )
    body: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": "You are a concise summarizer."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "agent_plain_completion": True,
        "temperature": 0.3,
        "max_tokens": 350,
    }
    res = await chat_completion(body)
    try:
        return str(res["choices"][0]["message"]["content"]).strip()
    except Exception:
        return ""


def summarize(arguments: dict[str, Any]) -> str:
    ident = _identity()
    if ident is None:
        return _err("No user identity — rss.summarize needs an authenticated user.")
    tenant_id, caller_uid = ident

    persist = arguments.get("persist_dashboard")
    persist_dashboard = persist is not False and str(persist).lower() not in ("0", "false", "no")

    feeds = _feeds_from_arguments(arguments)
    wid: uuid.UUID | None = None
    data: dict[str, Any] = {}

    if not feeds:
        wid, res_err = resolve_dashboard_id(caller_uid, tenant_id, arguments.get("dashboard_id"))
        if wid is None:
            return _err(res_err or "dashboard_id required (or pass feed_urls)")
        ws = dashboard_db.dashboard_get(caller_uid, tenant_id, wid)
        if ws is None:
            return _err("dashboard not found or no access")
        data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
        feeds = _coerce_feed_rows(data)

    enabled_only = bool(arguments.get("enabled_only", True))
    if enabled_only:
        feeds = [f for f in feeds if f.get("enabled")]
    if not feeds:
        return _err("no feeds — add URLs via dashboard.list_append on data.feeds or pass feed_urls")

    language = str(arguments.get("language") or "de").strip().lower()
    max_items = arguments.get("max_items_per_feed")
    try:
        max_items_i = int(max_items) if max_items is not None else 10
    except (TypeError, ValueError):
        return _err("max_items_per_feed must be an integer")
    max_items_i = max(1, min(max_items_i, _MAX_ITEMS_PER_FEED))

    deliver_to_chat = bool(arguments.get("deliver_to_chat", False))
    conversation_id_raw = arguments.get("conversation_id")
    conversation_id: uuid.UUID | None = None
    if conversation_id_raw is not None and str(conversation_id_raw).strip():
        try:
            conversation_id = uuid.UUID(str(conversation_id_raw).strip())
        except (ValueError, TypeError):
            return _err("conversation_id must be a UUID when provided")

    async def _run() -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        ts = now.isoformat()
        items_out: list[dict[str, Any]] = []
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S, follow_redirects=True) as client:
            for f in feeds:
                url = str(f.get("url") or "").strip()
                if not url:
                    continue
                try:
                    resp = await client.get(url, headers={"User-Agent": "AgentLayer RSS/1.0"})
                    resp.raise_for_status()
                    parsed = feedparser.parse(resp.text)
                    entries = list(parsed.entries or [])[:max_items_i]
                except Exception as e:
                    errors.append(f"feed fetch failed: {url} ({e})")
                    continue

                for ent in entries:
                    a_url = str(getattr(ent, "link", "") or "").strip()
                    a_title = str(getattr(ent, "title", "") or "").strip() or "(untitled)"
                    try:
                        a_content = str(
                            getattr(ent, "summary", "") or getattr(ent, "description", "") or ""
                        )
                    except Exception:
                        a_content = ""
                    if not a_content.strip():
                        a_content = a_title

                    summary = await _summarize_one(
                        title=a_title, url=a_url or "", content=a_content, language=language
                    )
                    if not summary:
                        continue
                    items_out.append(
                        {"ts": ts, "title": a_title, "url": a_url or "", "summary": summary}
                    )

        md = "# RSS Summary\n\n"
        md += f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        for it in items_out[:200]:
            t, u, s = it.get("title") or "", it.get("url") or "", it.get("summary") or ""
            if u:
                md += f"## [{t}]({u})\n\n{s}\n\n---\n\n"
            else:
                md += f"## {t}\n\n{s}\n\n---\n\n"
        if not items_out:
            md += "_No items summarized._\n"

        result: dict[str, Any] = {
            "ok": True,
            "items": len(items_out),
            "errors": errors,
            "markdown": md,
            "history_items": items_out,
        }
        if wid is not None:
            result["dashboard_id"] = str(wid)

        if persist_dashboard:
            if wid is None:
                return {
                    "ok": False,
                    "error": "persist_dashboard requires dashboard_id (or omit persist_dashboard to get markdown only)",
                    "markdown": md,
                }
            from apps.backend.domain.collections import service as domain_svc

            ws_full = dashboard_db.dashboard_get(caller_uid, tenant_id, wid)
            if ws_full is None:
                return {"ok": False, "error": "failed to update (no access?)"}
            bindings = domain_svc.resolve_bindings_for_dashboard(ws_full)
            owner_raw = ws_full.get("owner_user_id")
            try:
                owner_uid = (
                    caller_uid
                    if not owner_raw
                    else uuid.UUID(str(owner_raw))
                )
            except (ValueError, TypeError):
                owner_uid = caller_uid
            patch_res = domain_svc.patch_fields(
                owner_user_id=owner_uid,
                tenant_id=int(ws_full.get("tenant_id") or tenant_id),
                bindings=bindings,
                ui_layout=ws_full.get("ui_layout") if isinstance(ws_full.get("ui_layout"), dict) else None,
                patches=[{"path": "latest_summary", "value": md}],
            )
            if not patch_res.get("ok"):
                return {"ok": False, "error": str(patch_res.get("error") or "domain persist failed")}
            if items_out:
                domain_svc.append_items(
                    owner_user_id=owner_uid,
                    tenant_id=int(ws_full.get("tenant_id") or tenant_id),
                    bindings=bindings,
                    ui_layout=ws_full.get("ui_layout") if isinstance(ws_full.get("ui_layout"), dict) else None,
                    list_path="history",
                    rows=items_out,
                )
            result["persisted"] = True
            result["source"] = "domain"
        else:
            result["persisted"] = False
            result["hint"] = "Use dashboard.patch_data to set latest_summary and append history"

        if deliver_to_chat:
            conv_id = conversation_id
            if conv_id is None:
                conv = conversation_create(
                    caller_uid,
                    title="RSS Summary",
                    mode="chat",
                    model="",
                    messages=[],
                    agent_log=[],
                    dashboard_id=None,
                    shared=False,
                )
                try:
                    conv_id = uuid.UUID(str(conv.get("id") or "").strip())
                except Exception:
                    conv_id = None
            if conv_id is not None:
                result["delivered_to_chat"] = conversation_append_message(
                    caller_uid, conv_id, role="assistant", content=md
                )
                result["conversation_id"] = str(conv_id)

        return result

    id_tok = set_identity(tenant_id, caller_uid)
    try:
        out = json.loads(json.dumps(asyncio.run(_run()), ensure_ascii=False))
    finally:
        reset_identity(id_tok)
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "summarize": summarize,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "summarize",
            "description": (
                "Fetch and summarize RSS feeds. Sources: feed_urls or dashboard.data.feeds "
                "(dashboard.read / list_append). persist_dashboard=false returns markdown only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "description": "Feeds board UUID; optional if only one board or using feed_urls.",
                    },
                    "feed_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional RSS URLs (skips dashboard feed list).",
                    },
                    "persist_dashboard": {
                        "type": "boolean",
                        "description": "Write latest_summary + history to dashboard (default true).",
                    },
                    "max_items_per_feed": {"type": "integer", "description": "Default 10 (max 15)."},
                    "enabled_only": {"type": "boolean", "description": "Default true for dashboard feeds."},
                    "language": {"type": "string", "description": "de or en (default de)."},
                    "deliver_to_chat": {"type": "boolean"},
                    "conversation_id": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]
