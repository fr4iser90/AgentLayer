"""Mail integration helpers (IMAP/SMTP) — colocated with mail tools, not backend domain."""

from plugins.tools.integrations.mail.lib.providers import MAIL_PROVIDERS, MailProviderSpec
from plugins.tools.integrations.mail.lib.resolve import MailSession, resolve_mail_session

__all__ = ["MAIL_PROVIDERS", "MailProviderSpec", "MailSession", "resolve_mail_session"]
