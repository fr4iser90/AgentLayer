"""Mail provider resolution and shared IMAP helpers (not tool modules)."""

from apps.backend.domain.mail.providers import MAIL_PROVIDERS, MailProviderSpec
from apps.backend.domain.mail.resolve import resolve_mail_session

__all__ = ["MAIL_PROVIDERS", "MailProviderSpec", "resolve_mail_session"]
