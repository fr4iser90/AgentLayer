"""Mail provider definitions (brand / IMAP endpoint — not TOOL_DOMAIN)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MailProviderSpec:
    id: str
    label: str
    imap_host: str
    imap_port: int = 993
    secret_keys: tuple[str, ...] = ()
    uses_gmail_raw: bool = False
    default_query: str = "INBOX"
    secret_form: dict[str, Any] = field(default_factory=dict)


MAIL_PROVIDERS: dict[str, MailProviderSpec] = {
    "gmail": MailProviderSpec(
        id="gmail",
        label="Gmail",
        imap_host="imap.gmail.com",
        secret_keys=("gmail", "mail"),
        uses_gmail_raw=True,
        default_query="in:inbox",
        secret_form={
            "title": "Gmail (IMAP)",
            "help": (
                "Google **App Password** (16 characters), not your normal password. "
                "Account → Security → 2-Step Verification → App passwords."
            ),
            "fields": [
                {"name": "email", "label": "Gmail address", "type": "email", "required": True},
                {"name": "app_password", "label": "App password", "type": "password", "required": True},
            ],
        },
    ),
    "outlook": MailProviderSpec(
        id="outlook",
        label="Outlook / Microsoft 365",
        imap_host="outlook.office365.com",
        secret_keys=("outlook", "mail"),
        default_query="INBOX",
        secret_form={
            "title": "Outlook (IMAP)",
            "help": "Enable IMAP in Outlook settings; use an app password if MFA is on.",
            "fields": [
                {"name": "email", "label": "Email address", "type": "email", "required": True},
                {"name": "password", "label": "Password or app password", "type": "password", "required": True},
            ],
        },
    ),
    "gmx": MailProviderSpec(
        id="gmx",
        label="GMX",
        imap_host="imap.gmx.net",
        secret_keys=("gmx", "mail"),
        secret_form={
            "title": "GMX (IMAP)",
            "help": "Enable IMAP in GMX settings (POP3 & IMAP).",
            "fields": [
                {"name": "email", "label": "GMX address", "type": "email", "required": True},
                {"name": "password", "label": "Password", "type": "password", "required": True},
            ],
        },
    ),
    "yahoo": MailProviderSpec(
        id="yahoo",
        label="Yahoo Mail",
        imap_host="imap.mail.yahoo.com",
        secret_keys=("yahoo", "mail"),
        secret_form={
            "title": "Yahoo Mail (IMAP)",
            "help": "Generate an app password in Yahoo account security settings.",
            "fields": [
                {"name": "email", "label": "Yahoo address", "type": "email", "required": True},
                {"name": "app_password", "label": "App password", "type": "password", "required": True},
            ],
        },
    ),
    "proton": MailProviderSpec(
        id="proton",
        label="Proton Mail (Bridge)",
        imap_host="127.0.0.1",
        imap_port=1143,
        secret_keys=("proton", "mail"),
        secret_form={
            "title": "Proton Mail (Bridge)",
            "help": "Requires Proton Mail Bridge running locally with IMAP enabled.",
            "fields": [
                {"name": "email", "label": "Proton address", "type": "email", "required": True},
                {"name": "password", "label": "Bridge mailbox password", "type": "password", "required": True},
            ],
        },
    ),
}


def provider_ids() -> list[str]:
    return sorted(MAIL_PROVIDERS.keys())
