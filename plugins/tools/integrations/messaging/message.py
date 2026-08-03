"""Send messages to friends/contacts via Telegram, Discord, or email (operator bots + mail.send)."""

from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from apps.backend.infrastructure.platform.config import PUBLIC_BASE_URL
from plugins.tools.integrations.messaging.lib.outbound import OutboundDeliveryError, send_discord_to_user, send_telegram_to_user
from plugins.tools.integrations.friends.lib.common import resolve_contact_email, resolve_message_recipient
from apps.backend.domain.shared.identity import get_identity
from apps.backend.infrastructure.identity.auth import get_user_by_email

__version__ = "1.0.0"
TOOL_ID = "message"
TOOL_BUCKET = "comms"
TOOL_DOMAIN = "messaging"
# Router phrases: co-located message.router.yaml (all locales unioned at load).
TOOL_TRIGGERS: tuple[str, ...] = ()
TOOL_LABEL = "Messaging"
TOOL_DESCRIPTION = (
    "Send a message to a friend or contact via Telegram, Discord, or email. "
    "Uses operator bots (Admin → Interfaces) and linked ids (Settings → Connections). "
    "channel=auto: telegram → discord → email. Outbound only — use dashboard.* to persist board data."
)
TOOL_CAPABILITIES = ("messaging.send", "mail.send", "friends.user")
TOOL_RISK_LEVEL = 3
TOOL_FAMILIES = ("communication",)


def _full_link(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    base = (PUBLIC_BASE_URL or "").strip().rstrip("/")
    if base:
        return f"{base}{p}" if p.startswith("/") else f"{base}/{p}"
    return p


def _append_upload_hint(body: str, *, photo_upload_hint: bool) -> str:
    if not photo_upload_hint:
        return body
    hint = (
        "\n\nFotos: Schick sie als Bild direkt an diesen Telegram-Bot — "
        "sie landen im geteilten Album (wenn du Bearbeitungs-Recht auf dem Dashboard hast)."
    )
    return (body.rstrip() + hint)[:4000]


def send(arguments: dict[str, Any]) -> str:
    tid, uid = get_identity()
    if uid is None:
        return json.dumps({"ok": False, "error": "No user identity"}, ensure_ascii=False)

    to_raw = str(
        arguments.get("to") or arguments.get("name") or arguments.get("email") or arguments.get("entity") or ""
    ).strip()
    if not to_raw:
        return json.dumps({"ok": False, "error": "to or name is required"}, ensure_ascii=False)

    body = str(arguments.get("body") or arguments.get("text") or arguments.get("message") or "").strip()
    if not body:
        return json.dumps({"ok": False, "error": "body is required"}, ensure_ascii=False)

    channel = str(arguments.get("channel") or "auto").strip().lower()
    dry_run = bool(arguments.get("dry_run"))
    photo_upload_hint = bool(
        arguments.get("photo_upload_hint") or arguments.get("telegram_upload")
    )
    link_path = str(arguments.get("link_path") or "").strip()
    if link_path:
        body = f"{body}\n\n{_full_link(link_path)}".strip()

    body = _append_upload_hint(body, photo_upload_hint=photo_upload_hint)

    recipient = resolve_message_recipient(uid, to_raw)
    if recipient is None and "@" in to_raw:
        target = get_user_by_email(to_raw.lower())
        if target:
            from plugins.tools.integrations.friends.lib.common import _recipient_from_user_uuid

            recipient = _recipient_from_user_uuid(
                target.id,
                {"email": to_raw.lower(), "display_name": to_raw},
            )
    if recipient is None:
        return json.dumps(
            {"ok": False, "error": f"could not resolve contact {to_raw!r}"},
            ensure_ascii=False,
        )

    friend_uid: uuid.UUID | None = None
    if recipient.get("friend_user_id"):
        friend_uid = uuid.UUID(str(recipient["friend_user_id"]))

    channels_to_try: list[str]
    if channel == "auto":
        channels_to_try = ["telegram", "discord", "email"]
    else:
        channels_to_try = [channel]

    if dry_run:
        return json.dumps(
            {
                "ok": True,
                "dry_run": True,
                "to": to_raw,
                "recipient": recipient,
                "channel_requested": channel,
                "body": body,
                "photo_upload_hint": photo_upload_hint,
            },
            ensure_ascii=False,
        )

    errors: list[str] = []
    for ch in channels_to_try:
        if ch == "telegram":
            if not friend_uid:
                errors.append("telegram: contact is not a confirmed friend with AgentLayer account")
                continue
            if not recipient.get("telegram_user_id"):
                errors.append("telegram: recipient has no linked Telegram user id")
                continue
            try:
                result = send_telegram_to_user(
                    sender_user_id=uid,
                    recipient_user_id=friend_uid,
                    text=body,
                )
                return json.dumps({**result, "to": to_raw, "body_sent": body[:500]}, ensure_ascii=False)
            except OutboundDeliveryError as e:
                errors.append(f"telegram: {e}")
                continue
        if ch == "discord":
            if not friend_uid:
                errors.append("discord: contact is not a confirmed friend with AgentLayer account")
                continue
            dc = recipient.get("discord_user_id")
            if not dc:
                errors.append("discord: recipient has no linked Discord user id")
                continue
            try:
                result = send_discord_to_user(
                    sender_user_id=uid,
                    recipient_user_id=friend_uid,
                    text=body,
                )
                return json.dumps({**result, "to": to_raw, "body_sent": body[:500]}, ensure_ascii=False)
            except OutboundDeliveryError as e:
                errors.append(f"discord: {e}")
                continue
        if ch == "email":
            from plugins.tools.integrations.mail.tools import mail as mail_tools

            em = recipient.get("email") or resolve_contact_email(uid, to_raw)
            if not em:
                errors.append("email: no email for recipient")
                continue
            mail_args = {
                "to": em,
                "subject": str(arguments.get("subject") or "AgentLayer"),
                "body": body,
            }
            if arguments.get("provider"):
                mail_args["provider"] = arguments["provider"]
            out = mail_tools.send(mail_args)
            parsed = json.loads(out)
            if parsed.get("ok"):
                parsed["channel"] = "email"
                parsed["to"] = to_raw
                return json.dumps(parsed, ensure_ascii=False)
            errors.append(f"email: {parsed.get('error') or 'send failed'}")
            continue
        return json.dumps({"ok": False, "error": f"unknown channel {ch!r}"}, ensure_ascii=False)

    return json.dumps(
        {"ok": False, "error": "could not deliver message", "attempts": errors},
        ensure_ascii=False,
    )


HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "send": send,
}

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send",
            "TOOL_DESCRIPTION": (
                "Send a message to a friend/contact by name or email. "
                "channel: telegram | discord | email | auto (default: telegram → discord → email). "
                "Recipient must have linked Telegram/Discord under Settings → Connections (for those channels). "
                "Set photo_upload_hint=true when inviting photo uploads via Telegram bot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "TOOL_DESCRIPTION": "Contact name or email (e.g. Sandra)"},
                    "name": {"type": "string", "TOOL_DESCRIPTION": "Alias for to"},
                    "body": {"type": "string", "TOOL_DESCRIPTION": "Message text"},
                    "subject": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Email subject only (default AgentLayer)",
                    },
                    "channel": {
                        "type": "string",
                        "enum": ["auto", "telegram", "discord", "email"],
                        "TOOL_DESCRIPTION": "Delivery channel (default auto)",
                    },
                    "link_path": {
                        "type": "string",
                        "TOOL_DESCRIPTION": "Optional app path appended as full URL (e.g. /app/dashboards)",
                    },
                    "photo_upload_hint": {
                        "type": "boolean",
                        "TOOL_DESCRIPTION": (
                            "Append Telegram photo-upload instructions. Requires edit access on the "
                            "dashboard (friends.shares with permission=edit, invite_member, or block_share_grant)."
                        ),
                    },
                    "dry_run": {"type": "boolean", "TOOL_DESCRIPTION": "Preview without sending"},
                    "provider": {"type": "string", "TOOL_DESCRIPTION": "Mail provider when channel=email"},
                },
                "required": ["to", "body"],
            },
        },
    },
]
