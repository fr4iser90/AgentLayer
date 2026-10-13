"""Track system-context injections for transparent chat UI badges + digests.

DSH-style once+on-change for the LLM:
- Digests persist per conversation/agent.
- When ``skip_llm_when_unchanged`` is on, unchanged *omitable* kinds are not
  re-appended to the system prefix (real token savings). A short stub lists
  what was omitted. Identity/persona-style kinds always re-send.
- After history compaction (or periodic refresh), digests for omitable kinds
  are cleared so the next turn re-injects full bodies.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

# Soft cap per body sent to the client (full text still goes to the model when sent).
_DEFAULT_BODY_MAX = 8_000
_MAX_RECORDS = 40

# Kinds that are stable across turns — hash-gated for UI + optional LLM omit.
ON_CHANGE_INJECT_KINDS = frozenset(
    {
        "agent_system_prompt",
        "system_extra",
        "skills",
        "persona",
        "secrets_bootstrap",
        "workspace_bound",
        "agents_md",
        "workspace_verify",
        "workspace_retrieval",
        "dashboard",
        "profession",
        "delegate_catalog",
        "agent_tasks",
        "media_library",
        "knowledge_orchestration",
        "conversation_goal",
    }
)

# Recoverable via workspace/tools — safe to omit from the LLM when digest matches.
OMIT_WHEN_UNCHANGED_KINDS = frozenset(
    {
        "skills",
        "secrets_bootstrap",
        "workspace_bound",
        "agents_md",
        "workspace_verify",
        "workspace_retrieval",
        "dashboard",
        "delegate_catalog",
        "agent_tasks",
        "media_library",
        "knowledge_orchestration",
    }
)

# Always send full body even when digest matches (identity / soft state).
ALWAYS_SEND_KINDS = frozenset(
    {
        "agent_system_prompt",
        "system_extra",
        "persona",
        "profession",
        "conversation_goal",
    }
)

_ledger: ContextVar[list["InjectRecord"] | None] = ContextVar(
    "agentlayer_context_inject_ledger", default=None
)
_prior_digests: ContextVar[dict[str, str] | None] = ContextVar(
    "agentlayer_context_inject_prior_digests", default=None
)
_new_digests: ContextVar[dict[str, str] | None] = ContextVar(
    "agentlayer_context_inject_new_digests", default=None
)
_skip_llm: ContextVar[bool] = ContextVar(
    "agentlayer_context_inject_skip_llm", default=False
)
_omitted: ContextVar[list[tuple[str, str, int]] | None] = ContextVar(
    "agentlayer_context_inject_omitted", default=None
)


@dataclass(frozen=True)
class InjectRecord:
    kind: str
    label: str
    body: str
    chars: int
    digest: str
    unchanged: bool = False

    def to_public(self, *, body_max: int = _DEFAULT_BODY_MAX) -> dict[str, Any]:
        body = self.body
        truncated = False
        if self.unchanged:
            body = ""
        elif len(body) > body_max:
            body = body[:body_max].rstrip() + "\n…(truncated for UI)"
            truncated = True
        return {
            "kind": self.kind,
            "label": self.label,
            "body": body,
            "chars": self.chars,
            "truncated": truncated,
            "digest": self.digest,
            "unchanged": self.unchanged,
        }


def begin_inject_ledger(
    *,
    prior_digests: dict[str, str] | None = None,
    skip_llm_when_unchanged: bool = False,
) -> Token:
    """Start ledger; optional prior digests from conversation store (this agent)."""
    _prior_digests.set(dict(prior_digests or {}))
    _new_digests.set({})
    _skip_llm.set(bool(skip_llm_when_unchanged))
    _omitted.set([])
    return _ledger.set([])


def take_inject_ledger(token: Token) -> list[dict[str, Any]]:
    records = list(_ledger.get() or [])
    _ledger.reset(token)
    return [r.to_public() for r in records[:_MAX_RECORDS]]


def take_inject_digests() -> dict[str, str]:
    """Return updated digests for on-change kinds after a turn (for persistence)."""
    prior = dict(_prior_digests.get() or {})
    new = dict(_new_digests.get() or {})
    merged = {**prior, **new}
    _prior_digests.set(None)
    _new_digests.set(None)
    _skip_llm.set(False)
    return merged


def take_omitted_injects() -> list[tuple[str, str, int]]:
    """Return ``(kind, label, chars)`` omitted from the LLM this turn."""
    rows = list(_omitted.get() or [])
    _omitted.set(None)
    return rows


def inject_omit_stub(omitted: list[tuple[str, str, int]]) -> str:
    """Short system note listing omitted stable context blocks."""
    if not omitted:
        return ""
    bits: list[str] = []
    for kind, label, chars in omitted:
        lab = (label or kind).strip() or kind
        bits.append(f"{lab} ({chars} chars)")
    listed = ", ".join(bits)
    return (
        "[Stable context unchanged — omitted to save tokens: "
        f"{listed}]\n"
        "These blocks were provided earlier in this conversation and remain in effect. "
        "Re-read via workspace tools (e.g. AGENTS.md, skills files) if you need the full text."
    )


def inject_body_digest(kind: str, body: str) -> str:
    raw = f"{(kind or '').strip()}\n{(body or '').strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def clear_omitable_digests(digests: dict[str, str]) -> dict[str, str]:
    """Drop omitable kind digests (force full re-inject next turn)."""
    return {k: v for k, v in digests.items() if k not in OMIT_WHEN_UNCHANGED_KINDS}


def record_injection(
    kind: str,
    body: str,
    *,
    label: str | None = None,
) -> bool:
    """
    Append one inject record when a ledger is active.

    Returns True if the body should be appended to the LLM system message,
    False if this on-change inject is unchanged and omit is enabled for the kind.
    """
    ledger = _ledger.get()
    if ledger is None:
        return True
    text = (body or "").strip()
    if not text:
        return False
    k = (kind or "system").strip() or "system"
    lab = (label or k).strip() or k
    if k == "secrets_bootstrap":
        text = text[:_DEFAULT_BODY_MAX]
    digest = inject_body_digest(k, text)
    prior = _prior_digests.get() or {}
    new_map = _new_digests.get()
    if new_map is None:
        new_map = {}
        _new_digests.set(new_map)

    unchanged = False
    if k in ON_CHANGE_INJECT_KINDS and prior.get(k) == digest:
        unchanged = True
    if k in ON_CHANGE_INJECT_KINDS:
        new_map[k] = digest

    omit_llm = (
        unchanged
        and _skip_llm.get()
        and k in OMIT_WHEN_UNCHANGED_KINDS
        and k not in ALWAYS_SEND_KINDS
    )

    if omit_llm:
        omitted = _omitted.get()
        if omitted is None:
            omitted = []
            _omitted.set(omitted)
        omitted.append((k, lab, len(text)))
        # Not sent to the LLM → do not surface in the chat UI badge list.
        return False

    if len(ledger) >= _MAX_RECORDS:
        return True

    # UI ledger = only blocks actually appended to the LLM this turn.
    ledger.append(
        InjectRecord(
            kind=k,
            label=lab,
            body=text,
            chars=len(text),
            digest=digest,
            unchanged=False,
        )
    )
    return True
