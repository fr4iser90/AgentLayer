"""RSS tools for `kind: feeds` dashboards — summarize enabled feed URLs into dashboard data."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

import feedparser
import httpx

from apps.backend.domain.agent import chat_completion
from apps.backend.domain.identity import get_identity, reset_identity, set_identity
from apps.backend.infrastructure.conversations_db import conversation_append_message, conversation_create
from apps.backend.dashboard import db as dashboard_db
from apps.backend.dashboard.tool_dashboard_resolve import (
    resolve_dashboard_id_for_kind,
    dashboard_rows_for_kind,
)

__version__ = "0.1.0"
TOOL_ID = "rss"
TOOL_BUCKET = "productivity"
TOOL_DOMAIN = "productivity"
TOOL_LABEL = "RSS feeds"
TOOL_DESCRIPTION = (
    "Read and update RSS feed dashboards (kind feeds). Use this to fetch + summarize enabled feed URLs and "
    "store the latest markdown summary back into the dashboard (latest_summary + history)."
)
TOOL_TRIGGERS = ("rss", "feed", "feeds", "news", "summary", "summarize feeds", "rss summary")
TOOL_CAPABILITIES = ("dashboard.feeds.read", "dashboard.feeds.write")
TOOL_MIN_ROLE = "user"

AGENT_TOOL_META_BY_NAME = {
    "feeds_dashboards": {"min_role": "user", "capabilities": ("dashboard.feeds.read",)},
    "feeds_summarize": {"min_role": "user", "capabilities": ("dashboard.feeds.write",)},
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


def feeds_dashboards(arguments: dict[str, Any]) -> str:
    """List feeds dashboards for the current user."""
    del arguments
    ident = _identity()
    if ident is None:
        return _err("No user identity — feeds tools need an authenticated chat user.")
    tid, uid = ident
    rows = dashboard_rows_for_kind(uid, tid, "feeds")
    out = [{"id": str(r.get("id", "")), "title": (r.get("title") or "").strip()} for r in rows]
    return json.dumps({"ok": True, "dashboards": out}, ensure_ascii=False)


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


def feeds_summarize(arguments: dict[str, Any]) -> str:
    """
    Fetch enabled RSS feeds from a feeds dashboard and write results back to dashboard.data.

    Writes:
    - data.latest_summary: markdown
    - data.history: append {ts,title,summary,url}
    """
    ident = _identity()
    if ident is None:
        return _err("No user identity — feeds tools need an authenticated chat user.")
    tenant_id, caller_uid = ident

    wid, res_err = resolve_dashboard_id_for_kind(
        caller_uid, tenant_id, kind="feeds", raw_dashboard_id=arguments.get("dashboard_id")
    )
    if wid is None:
        return _err(res_err or "dashboard_id required")

    ws = dashboard_db.dashboard_get(caller_uid, tenant_id, wid)
    if ws is None:
        return _err("dashboard not found or no access")
    if (ws.get("kind") or "").strip() != "feeds":
        return _err("dashboard is not a feeds kind")

    language = str(arguments.get("language") or "de").strip().lower()
    max_items = arguments.get("max_items_per_feed")
    try:
        max_items_i = int(max_items) if max_items is not None else 10
    except (TypeError, ValueError):
        return _err("max_items_per_feed must be an integer")
    if max_items_i < 1:
        max_items_i = 1
    if max_items_i > _MAX_ITEMS_PER_FEED:
        max_items_i = _MAX_ITEMS_PER_FEED

    enabled_only = bool(arguments.get("enabled_only", True))
    deliver_to_chat = bool(arguments.get("deliver_to_chat", False))
    conversation_id_raw = arguments.get("conversation_id")
    conversation_id: uuid.UUID | None = None
    if conversation_id_raw is not None and str(conversation_id_raw).strip():
        try:
            conversation_id = uuid.UUID(str(conversation_id_raw).strip())
        except (ValueError, TypeError):
            return _err("conversation_id must be a UUID when provided")

    data = ws.get("data") if isinstance(ws.get("data"), dict) else {}
    feeds = _coerce_feed_rows(data)
    if enabled_only:
        feeds = [f for f in feeds if f.get("enabled")]
    if not feeds:
        return _err("no feeds configured (add rows to data.feeds in the dashboard UI)")

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
                    a_content = ""
                    try:
                        a_content = str(getattr(ent, "summary", "") or getattr(ent, "description", "") or "")
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
                        {
                            "ts": ts,
                            "title": a_title,
                            "url": a_url or "",
                            "summary": summary,
                        }
                    )

        # Build markdown
        md = "# RSS Summary\n\n"
        md += f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        for it in items_out[:200]:
            t = it.get("title") or ""
            u = it.get("url") or ""
            s = it.get("summary") or ""
            if u:
                md += f"## [{t}]({u})\n\n{s}\n\n---\n\n"
            else:
                md += f"## {t}\n\n{s}\n\n---\n\n"
        if not items_out:
            md += "_No items summarized._\n"

        # Persist dashboard update
        cur_data = dict(data) if isinstance(data, dict) else {}
        hist = cur_data.get("history")
        if not isinstance(hist, list):
            hist = []
        hist2 = list(hist) + items_out
        if len(hist2) > _MAX_HISTORY:
            hist2 = hist2[-_MAX_HISTORY:]
        cur_data["latest_summary"] = md
        cur_data["history"] = hist2
        updated = dashboard_db.dashboard_update(caller_uid, tenant_id, wid, data=cur_data)
        if updated is None:
            return {"ok": False, "error": "failed to update dashboard (no write access?)"}

        delivered = False
        conv_id_out: str | None = None
        if deliver_to_chat:
            # Personal chat thread (per-user). If no conversation_id is given, create a fresh one.
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
                delivered = conversation_append_message(
                    caller_uid,
                    conv_id,
                    role="assistant",
                    content=md,
                )
                conv_id_out = str(conv_id)

        return {
            "ok": True,
            "dashboard_id": str(wid),
            "items": len(items_out),
            "errors": errors,
            "delivered_to_chat": delivered,
            "conversation_id": conv_id_out,
        }

    # Ensure identity stays the same for nested chat_completion calls (tool execution is synchronous).
    id_tok = set_identity(tenant_id, caller_uid)
    try:
        out = json.loads(json.dumps(asyncio.run(_run()), ensure_ascii=False))
    finally:
        reset_identity(id_tok)
    return json.dumps(out, ensure_ascii=False)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "feeds_dashboards": feeds_dashboards,
    "feeds_summarize": feeds_summarize,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "feeds_dashboards",
            "TOOL_DESCRIPTION": "List your feeds dashboards (kind feeds) with ids + titles.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "feeds_summarize",
            "TOOL_DESCRIPTION": (
                "Fetch + summarize enabled RSS feeds from a feeds dashboard and write results back to "
                "dashboard.data.latest_summary and dashboard.data.history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "dashboard_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Feeds dashboard UUID. Optional if you only have one feeds dashboard.",
                    },
                    "max_items_per_feed": {"type": "integer", "TOOL_DESCRIPTION": "Default 10 (max 15)."},
                    "enabled_only": {"type": "boolean", "TOOL_DESCRIPTION": "Default true."},
                    "language": {"type": "string", "TOOL_DESCRIPTION": "de or en (default de)."},
                    "deliver_to_chat": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": "If true, append the markdown summary to a personal chat conversation.",
                    },
                    "conversation_id": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional UUID of an existing personal conversation to append to.",
                    },
                },
                "required": [],
            },
        },
    },
]

