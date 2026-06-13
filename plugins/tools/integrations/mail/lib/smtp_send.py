"""Send email via SMTP using the same credentials as IMAP mail tools."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from plugins.tools.integrations.mail.lib.providers import MAIL_PROVIDERS, MailProviderSpec
from plugins.tools.integrations.mail.lib.resolve import MailSession

# Provider SMTP endpoints (STARTTLS on submission port).
_SMTP_BY_PROVIDER: dict[str, tuple[str, int]] = {
    "gmail": ("smtp.gmail.com", 587),
    "outlook": ("smtp.office365.com", 587),
    "gmx": ("mail.gmx.net", 587),
    "yahoo": ("smtp.mail.yahoo.com", 587),
    "proton": ("127.0.0.1", 1025),
}


def smtp_endpoint(spec: MailProviderSpec) -> tuple[str, int]:
    return _SMTP_BY_PROVIDER.get(spec.id, (spec.imap_host.replace("imap.", "smtp.", 1), 587))


def send_mail_message(
    session: MailSession,
    *,
    to_addrs: list[str],
    subject: str,
    body_text: str,
    cc_addrs: list[str] | None = None,
) -> dict[str, Any]:
    """Send a plain-text email. Returns ``{ok: True, ...}`` or raises ``ValueError``."""
    recipients = [a.strip() for a in to_addrs if a and str(a).strip()]
    if not recipients:
        raise ValueError("at least one recipient is required")
    cc = [a.strip() for a in (cc_addrs or []) if a and str(a).strip()]
    subj = (subject or "").strip()
    if not subj:
        raise ValueError("subject is required")
    body = (body_text or "").strip()
    if not body:
        raise ValueError("body_text is required")

    msg = EmailMessage()
    msg["From"] = session.email
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subj[:500]
    msg.set_content(body[:100_000])

    host, port = smtp_endpoint(session.provider)
    all_rcpt = recipients + cc
    with smtplib.SMTP(host, port, timeout=60) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(session.email, session.password)
        smtp.send_message(msg, from_addr=session.email, to_addrs=all_rcpt)

    return {
        "ok": True,
        "provider": session.provider.id,
        "from": session.email,
        "to": recipients,
        "cc": cc,
        "subject": subj,
    }
