"""Provider-specific IMAP search (UID lists)."""

from __future__ import annotations

import imaplib
import re

from apps.backend.domain.mail.providers import MailProviderSpec
from apps.backend.domain.mail.resolve import sanitize_query


def search_uids(
    mail: imaplib.IMAP4_SSL,
    query: str,
    limit: int,
    *,
    provider: MailProviderSpec,
) -> list[bytes]:
    limit = max(1, min(int(limit or 20), 50))
    q = sanitize_query(query, provider=provider)

    if provider.uses_gmail_raw:
        typ, data = mail.uid("SEARCH", None, "X-GM-RAW", f'"{q}"')
    else:
        typ, data = _standard_imap_search(mail, q)

    if typ != "OK" or not data or not data[0]:
        return []
    uids = data[0].split()
    if len(uids) > limit:
        uids = uids[-limit:]
    return list(reversed(uids))


def _standard_imap_search(mail: imaplib.IMAP4_SSL, query: str) -> tuple[str, list[bytes | None]]:
    q = query.strip()
    if not q or q.upper() == "INBOX":
        return mail.uid("SEARCH", None, "ALL")

    from_m = re.search(r"\bfrom:(\S+)", q, re.I)
    subj_m = re.search(r"\bsubject:(\S+)", q, re.I)
    if from_m:
        return mail.uid("SEARCH", None, "FROM", from_m.group(1))
    if subj_m:
        return mail.uid("SEARCH", None, "SUBJECT", subj_m.group(1))

    # Fallback: TEXT search on remaining terms
    text = re.sub(r"\b(from|subject):", "", q, flags=re.I).strip()
    if text:
        return mail.uid("SEARCH", None, "TEXT", text)
    return mail.uid("SEARCH", None, "ALL")
