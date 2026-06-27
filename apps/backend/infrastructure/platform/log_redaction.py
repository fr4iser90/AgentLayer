"""Strip secrets from log records (e.g. Telegram bot token embedded in ``httpx`` request URLs)."""

from __future__ import annotations

import logging
import re

# https://api.telegram.org/bot<token>/method — token is digits:alphanumeric
_TELEGRAM_BOT_PATH = re.compile(
    r"(https?://api\.telegram\.org/)bot[^/\s]+/",
    re.IGNORECASE,
)


def redact_sensitive_log_text(msg: str) -> str:
    return _TELEGRAM_BOT_PATH.sub(r"\1bot***REDACTED***/", msg)


class RedactSensitiveLogFilter(logging.Filter):
    """Applied to handlers so ``HTTP Request: POST https://api.telegram.org/bot…`` never prints the token."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            full = record.getMessage()
        except Exception:
            return True
        redacted = redact_sensitive_log_text(full)
        if redacted != full:
            record.msg = redacted
            record.args = ()
        return True


def apply_http_client_log_levels() -> None:
    """Set ``httpx`` / ``httpcore`` from ``operator_settings`` (Admin → Interfaces).

    If the DB row is not readable yet, uses ``WARNING``. Uvicorn may reset library loggers
    after import — call from FastAPI ``lifespan`` startup and after PATCH operator-settings.
    """
    try:
        from apps.backend.infrastructure.settings import operator_settings

        level = operator_settings.effective_http_client_log_level_int()
    except Exception:
        level = logging.WARNING
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(level)


def install_log_redaction_filters() -> None:
    """Attach before/after ``basicConfig``; also filter library loggers that may not use root only."""
    filt = RedactSensitiveLogFilter()
    root = logging.getLogger()
    root.addFilter(filt)
    for h in root.handlers:
        h.addFilter(filt)
    for name in ("httpx", "httpcore", "telegram", "telegram.ext"):
        logging.getLogger(name).addFilter(filt)

    apply_http_client_log_levels()
