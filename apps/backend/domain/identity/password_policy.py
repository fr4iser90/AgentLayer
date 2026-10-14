"""Shared password strength rules (setup admin + future account creates)."""

from __future__ import annotations

import re

MIN_PASSWORD_LENGTH = 12

_SEQ = (
    "0123456789",
    "9876543210",
    "abcdefghijklmnopqrstuvwxyz",
    "zyxwvutsrqponmlkjihgfedcba",
    "qwertyuiop",
    "asdfghjkl",
    "zxcvbnm",
)


def _has_long_sequence(lower: str, *, run: int = 4) -> bool:
    if len(lower) < run:
        return False
    for seq in _SEQ:
        for i in range(0, len(seq) - run + 1):
            if seq[i : i + run] in lower:
                return True
    return False


def _has_repeated_run(password: str, *, run: int = 4) -> bool:
    return bool(re.search(rf"(.)\1{{{run - 1},}}", password))


def password_rejection_reason(password: str) -> str | None:
    """Human-readable reason if the password is too weak; None if acceptable."""
    p = password or ""
    if len(p) < MIN_PASSWORD_LENGTH:
        return f"Passwort: mindestens {MIN_PASSWORD_LENGTH} Zeichen."
    if not re.search(r"[a-z]", p):
        return "Passwort: mindestens einen Kleinbuchstaben."
    if not re.search(r"[A-Z]", p):
        return "Passwort: mindestens einen Großbuchstaben."
    if not re.search(r"\d", p):
        return "Passwort: mindestens eine Ziffer."
    if not re.search(r"[^A-Za-z0-9]", p):
        return "Passwort: mindestens ein Sonderzeichen."
    lower = p.lower()
    if _has_long_sequence(lower) or _has_repeated_run(p):
        return "Passwort: keine einfachen Folgen oder Wiederholungen (z. B. 1234, aaaa)."
    return None


def password_strength_level(password: str) -> int:
    """
    0 empty, 1 weak (fails policy), 2 ok (passes), 3 strong (long + diverse).
    """
    p = password or ""
    if not p:
        return 0
    if password_rejection_reason(p) is not None:
        return 1
    if len(p) >= 16:
        return 3
    return 2
