"""Generic mail tools — domain ``mail``; provider chosen via secret or ``provider`` argument."""

from __future__ import annotations

import json
import imaplib
from typing import Any, Callable

from apps.backend.domain.mail.imap_common import (
    body_text_plain,
    connect_imap,
    decode_header_value,
    fetch_full_message,
    fetch_headers,
    select_mailbox,
)
from apps.backend.domain.mail.providers import MAIL_PROVIDERS
from apps.backend.domain.friends.common import resolve_contact_email
from apps.backend.domain.mail.resolve import resolve_mail_session, sanitize_query
from apps.backend.domain.mail.smtp_send import send_mail_message
from apps.backend.domain.mail.search import search_uids

__version__ = "2.0.0"
TOOL_ID = "mail"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "mail"
TOOL_TRIGGERS = (
    "mail",
    "email",
    "imap",
    "inbox",
    "gmail",
    "outlook",
    "gmx",
    "yahoo",
    "proton",
)
TOOL_LABEL = "Mail"
TOOL_DESCRIPTION = (
    "Search, read, and send email (IMAP + SMTP). Works with Gmail, Outlook, GMX, Yahoo, Proton (Bridge). "
    "Credentials from Settings → Connections. Does not write dashboards — store notes via dashboard.patch_data if needed."
)
TOOL_SECRETS_REQUIRED = tuple(
    sorted({k for spec in MAIL_PROVIDERS.values() for k in spec.secret_keys})
)
TOOL_CAPABILITIES = ("mail.read", "mail.search", "mail.send", "secrets.user")
TOOL_RISK_LEVEL = 2
TOOL_FAMILIES = ("communication", "productivity")

TOOL_USER_SECRET_FORMS: dict[str, dict[str, Any]] = {
    key: dict(spec.secret_form)
    for spec in MAIL_PROVIDERS.values()
    for key in spec.secret_keys
    if key != "mail"
}
TOOL_USER_SECRET_FORMS["mail"] = {
    "title": "Mail (any provider)",
    "help": 'JSON: {"provider":"gmail|outlook|gmx|yahoo|proton","email":"…","password":"…"}',
    "fields": [
        {"name": "provider", "label": "Provider id", "type": "text", "required": True},
        {"name": "email", "label": "Email address", "type": "email", "required": True},
        {"name": "password", "label": "Password / app password", "type": "password", "required": True},
    ],
}


def _query_from_args(arguments: dict[str, Any], provider_default: str) -> str:
    return (
        arguments.get("query")
        or arguments.get("gmail_query")
        or arguments.get("mail_query")
        or ""
    ).strip() or MAIL_PROVIDERS.get(provider_default, MAIL_PROVIDERS["gmail"]).default_query


def search(arguments: dict[str, Any]) -> str:
    session = resolve_mail_session(arguments)
    if isinstance(session, str):
        return json.dumps({"ok": False, "error": session}, ensure_ascii=False)

    spec = session.provider
    q = _query_from_args(arguments, spec.id)
    mailbox = (arguments.get("mailbox") or "INBOX").strip() or "INBOX"
    try:
        limit = int(arguments.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20

    try:
        mail = connect_imap(spec.imap_host, spec.imap_port, session.email, session.password)
    except imaplib.IMAP4.error as e:
        return json.dumps(
            {"ok": False, "error": f"IMAP login failed ({spec.id}): {e!s}"},
            ensure_ascii=False,
        )

    rows: list[dict[str, Any]] = []
    try:
        err = select_mailbox(mail, mailbox)
        if err:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        for uidb in search_uids(mail, q, limit, provider=spec):
            uid_s = uidb.decode("ascii", errors="replace") if isinstance(uidb, bytes) else str(uidb)
            hdr = fetch_headers(mail, uid_s)
            if not hdr:
                continue
            rows.append({"uid": int(uid_s), **hdr})
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    out: dict[str, Any] = {
        "ok": True,
        "provider": spec.id,
        "credentials_ok": True,
        "mailbox": mailbox,
        "query": sanitize_query(q, provider=spec),
        "count": len(rows),
        "messages": rows,
        "hint": "Use mail.read with uid from a row to fetch full text.",
    }
    if not rows:
        out["empty_result_note"] = "IMAP login succeeded but no messages matched this query."
    return json.dumps(out, ensure_ascii=False)


def read(arguments: dict[str, Any]) -> str:
    session = resolve_mail_session(arguments)
    if isinstance(session, str):
        return json.dumps({"ok": False, "error": session}, ensure_ascii=False)

    spec = session.provider
    try:
        uid = int(arguments.get("uid"))
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "uid is required (integer)"}, ensure_ascii=False)

    mailbox = (arguments.get("mailbox") or "INBOX").strip() or "INBOX"
    try:
        max_body = int(arguments.get("max_body_chars") or 24000)
    except (TypeError, ValueError):
        max_body = 24000
    max_body = max(1000, min(max_body, 100000))

    try:
        mail = connect_imap(spec.imap_host, spec.imap_port, session.email, session.password)
    except imaplib.IMAP4.error as e:
        return json.dumps(
            {"ok": False, "error": f"IMAP login failed ({spec.id}): {e!s}"},
            ensure_ascii=False,
        )

    try:
        err = select_mailbox(mail, mailbox)
        if err:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        msg = fetch_full_message(mail, uid)
        if msg is None:
            return json.dumps({"ok": False, "error": f"no message uid={uid}"}, ensure_ascii=False)
        body = body_text_plain(msg, max_body)
        return json.dumps(
            {
                "ok": True,
                "provider": spec.id,
                "uid": uid,
                "mailbox": mailbox,
                "from": decode_header_value(msg.get("From")),
                "to": decode_header_value(msg.get("To")),
                "subject": decode_header_value(msg.get("Subject")),
                "date": decode_header_value(msg.get("Date")),
                "body_text": body,
                "truncated": len(body) >= max_body,
            },
            ensure_ascii=False,
        )
    finally:
        try:
            mail.logout()
        except Exception:
            pass


def collect_for_summary(arguments: dict[str, Any]) -> str:
    session = resolve_mail_session(arguments)
    if isinstance(session, str):
        return json.dumps({"ok": False, "error": session}, ensure_ascii=False)

    spec = session.provider
    q = _query_from_args(arguments, spec.id)
    mailbox = (arguments.get("mailbox") or "INBOX").strip() or "INBOX"
    try:
        max_msg = int(arguments.get("max_messages") or 8)
    except (TypeError, ValueError):
        max_msg = 8
    max_msg = max(1, min(max_msg, 15))
    try:
        per = int(arguments.get("max_chars_per_message") or 6000)
    except (TypeError, ValueError):
        per = 6000
    per = max(500, min(per, 20000))

    try:
        mail = connect_imap(spec.imap_host, spec.imap_port, session.email, session.password)
    except imaplib.IMAP4.error as e:
        return json.dumps(
            {"ok": False, "error": f"IMAP login failed ({spec.id}): {e!s}"},
            ensure_ascii=False,
        )

    blocks: list[str] = []
    try:
        err = select_mailbox(mail, mailbox)
        if err:
            return json.dumps({"ok": False, "error": err}, ensure_ascii=False)
        uids = search_uids(mail, q, max_msg, provider=spec)
        if not uids:
            return json.dumps(
                {
                    "ok": True,
                    "provider": spec.id,
                    "count": 0,
                    "combined_excerpt": "",
                    "hint": "No messages matched.",
                },
                ensure_ascii=False,
            )
        for uidb in uids:
            uid_int = int(uidb.decode() if isinstance(uidb, bytes) else uidb)
            msg = fetch_full_message(mail, uid_int)
            if msg is None:
                continue
            subj = decode_header_value(msg.get("Subject"))
            frm = decode_header_value(msg.get("From"))
            dt = decode_header_value(msg.get("Date"))
            body = body_text_plain(msg, per)
            blocks.append(
                f"---\nUID: {uid_int}\nFrom: {frm}\nDate: {dt}\nSubject: {subj}\n\n{body}\n"
            )
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return json.dumps(
        {
            "ok": True,
            "provider": spec.id,
            "mailbox": mailbox,
            "query": sanitize_query(q, provider=spec),
            "count": len(blocks),
            "combined_excerpt": "\n".join(blocks),
        },
        ensure_ascii=False,
    )


def send(arguments: dict[str, Any]) -> str:
    session = resolve_mail_session(arguments)
    if isinstance(session, str):
        return json.dumps({"ok": False, "error": session}, ensure_ascii=False)

    to_raw = arguments.get("to") or arguments.get("email") or arguments.get("name")
    to_list: list[str] = []
    if isinstance(to_raw, list):
        to_list = [str(x).strip() for x in to_raw if str(x).strip()]
    elif to_raw is not None and str(to_raw).strip():
        to_list = [str(to_raw).strip()]

    resolved: list[str] = []
    from apps.backend.domain.identity import get_identity

    _tid, uid = get_identity()
    for entry in to_list:
        if "@" in entry:
            resolved.append(entry.lower())
            continue
        if uid is not None:
            em = resolve_contact_email(uid, entry)
            if em:
                resolved.append(em)
                continue
        return json.dumps(
            {"ok": False, "error": f"could not resolve email for recipient {entry!r}"},
            ensure_ascii=False,
        )

    subject = str(arguments.get("subject") or "").strip()
    body = str(arguments.get("body") or arguments.get("body_text") or "").strip()
    dry_run = bool(arguments.get("dry_run"))

    if dry_run:
        return json.dumps(
            {
                "ok": True,
                "dry_run": True,
                "provider": session.provider.id,
                "from": session.email,
                "to": resolved,
                "subject": subject,
                "body_text": body,
            },
            ensure_ascii=False,
        )

    try:
        result = send_mail_message(
            session,
            to_addrs=resolved,
            subject=subject,
            body_text=body,
            cc_addrs=arguments.get("cc") if isinstance(arguments.get("cc"), list) else None,
        )
    except ValueError as e:
        return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"ok": False, "error": f"SMTP send failed: {e!s}"}, ensure_ascii=False)

    return json.dumps(result, ensure_ascii=False)


def compose(arguments: dict[str, Any]) -> str:
    """Draft an outbound email without sending (same as send with dry_run=true)."""
    args = dict(arguments)
    args["dry_run"] = True
    return send(args)


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "search": search,
    "read": read,
    "collect_for_summary": collect_for_summary,
    "send": send,
    "compose": compose,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": TOOL_DESCRIPTION + " Search messages; returns uids and headers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "Optional: gmail, outlook, gmx, yahoo, proton (default: first configured secret)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (Gmail syntax for gmail; from:/subject:/text for others)",
                    },
                    "mailbox": {"type": "string", "description": "IMAP mailbox, default INBOX"},
                    "limit": {"type": "integer", "description": "Max messages (1–50, default 20)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read one email by IMAP UID from mail.search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "uid": {"type": "integer", "description": "UID from mail.search"},
                    "mailbox": {"type": "string"},
                    "max_body_chars": {"type": "integer"},
                },
                "required": ["uid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_for_summary",
            "description": "Fetch several messages into combined_excerpt for assistant summarization.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "query": {"type": "string"},
                    "mailbox": {"type": "string"},
                    "max_messages": {"type": "integer"},
                    "max_chars_per_message": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send",
            "description": (
                "Send a plain-text email via SMTP using the user's configured mail credentials. "
                "Recipient can be an email or a friend/contact name (resolved from the address book). "
                "Use dry_run=true to preview without sending."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "to": {
                        "type": "string",
                        "description": "Recipient email or contact name (e.g. Sandra)",
                    },
                    "email": {"type": "string", "description": "Alias for to"},
                    "name": {"type": "string", "description": "Alias for to (contact name)"},
                    "subject": {"type": "string"},
                    "body": {"type": "string", "description": "Plain-text message body"},
                    "body_text": {"type": "string", "description": "Alias for body"},
                    "cc": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional CC addresses",
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, return draft only — do not send",
                    },
                },
                "required": ["subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compose",
            "description": "Draft an outbound email (preview only, does not send). Same parameters as mail.send.",
            "parameters": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]
