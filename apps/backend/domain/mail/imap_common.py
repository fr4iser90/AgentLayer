"""Shared IMAP helpers for all mail providers."""

from __future__ import annotations

import imaplib
from email import message_from_bytes
from email.header import decode_header
from email.message import Message


def decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    chunks: list[str] = []
    for text, enc in parts:
        if isinstance(text, bytes):
            chunks.append(text.decode(enc or "utf-8", errors="replace"))
        else:
            chunks.append(str(text))
    return "".join(chunks)


def connect_imap(host: str, port: int, email: str, password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(host, port)
    mail.login(email, password)
    return mail


def select_mailbox(mail: imaplib.IMAP4_SSL, mailbox: str) -> str | None:
    mb = (mailbox or "INBOX").strip() or "INBOX"
    typ, _ = mail.select(mb, readonly=True)
    if typ != "OK":
        return f"cannot select mailbox {mb!r}"
    return None


def body_text_plain(msg: Message, max_chars: int) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype == "text/plain" and not part.get_filename():
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        t = payload.decode("utf-8", errors="replace")
                        return t[:max_chars] if len(t) > max_chars else t
                except Exception:
                    continue
        return ""
    try:
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        t = payload.decode("utf-8", errors="replace")
        return t[:max_chars] if len(t) > max_chars else t
    except Exception:
        return ""


def fetch_headers(
    mail: imaplib.IMAP4_SSL, uid_s: str
) -> dict[str, str] | None:
    typ, data = mail.uid(
        "FETCH", uid_s, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] UID)"
    )
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        return None
    raw = data[0][1]
    if not isinstance(raw, (bytes, bytearray)):
        return None
    h = message_from_bytes(bytes(raw))
    return {
        "from": decode_header_value(h.get("From")),
        "subject": decode_header_value(h.get("Subject")),
        "date": decode_header_value(h.get("Date")),
    }


def fetch_full_message(mail: imaplib.IMAP4_SSL, uid: int) -> Message | None:
    typ, data = mail.uid("FETCH", str(uid), "(RFC822)")
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        return None
    raw = data[0][1]
    if not isinstance(raw, (bytes, bytearray)):
        return None
    return message_from_bytes(bytes(raw))
