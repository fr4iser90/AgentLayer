"""Track system-context injections for transparent chat UI badges."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

# Soft cap per body sent to the client (full text still goes to the model).
_DEFAULT_BODY_MAX = 8_000
_MAX_RECORDS = 40

_ledger: ContextVar[list["InjectRecord"] | None] = ContextVar(
    "agentlayer_context_inject_ledger", default=None
)


@dataclass(frozen=True)
class InjectRecord:
    kind: str
    label: str
    body: str
    chars: int

    def to_public(self, *, body_max: int = _DEFAULT_BODY_MAX) -> dict[str, Any]:
        body = self.body
        truncated = False
        if len(body) > body_max:
            body = body[:body_max].rstrip() + "\n…(truncated for UI)"
            truncated = True
        return {
            "kind": self.kind,
            "label": self.label,
            "body": body,
            "chars": self.chars,
            "truncated": truncated,
        }


def begin_inject_ledger() -> Token:
    return _ledger.set([])


def take_inject_ledger(token: Token) -> list[dict[str, Any]]:
    records = list(_ledger.get() or [])
    _ledger.reset(token)
    return [r.to_public() for r in records[:_MAX_RECORDS]]


def record_injection(
    kind: str,
    body: str,
    *,
    label: str | None = None,
) -> None:
    """Append one inject record when a ledger is active; no-op otherwise."""
    ledger = _ledger.get()
    if ledger is None:
        return
    text = (body or "").strip()
    if not text:
        return
    k = (kind or "system").strip() or "system"
    # Never put credential-looking bootstrap bodies in the UI payload at full size;
    # secrets bootstrap is intentionally a key listing — still cap hard.
    lab = (label or k).strip() or k
    if k == "secrets_bootstrap":
        # Keep listing visible but avoid accidental secret echoes if format drifts.
        text = text[:_DEFAULT_BODY_MAX]
    if len(ledger) >= _MAX_RECORDS:
        return
    ledger.append(InjectRecord(kind=k, label=lab, body=text, chars=len(text)))
