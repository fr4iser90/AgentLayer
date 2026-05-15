"""Chat secret handling before LLM / DB persist (ADR 0006).

1. **Heuristic redaction** (``CHAT_SECRET_HEURISTIC_REDACT_ENABLED``, default **off**): optional regex
   masking for third-party LLM routes. Self-hosted setups often leave this off so configs/tokens in chat
   are not altered (Cursor-style: model sees the real values; you still persist chat — mind your DB backups).
2. **Optional vault** (``CHAT_SECRET_INGRESS_ENABLED`` + ``CHAT_SECRET_VAULT_FERNET_KEY``): whole-message
   JSON with keys ``discord_bot_token``, ``telegram_bot_token``, or ``api_key`` → encrypted vault +
   ``[[agentlayer:secret:<uuid>]]`` for operator tools to resolve and apply.

Declare-blocks were removed (opaque UX); use JSON + vault when you need apply, or enable heuristics for redact-only.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from typing import Any

import apps.backend.core.config as _cfgmod
from apps.backend.infrastructure import chat_secret_vault as _vault
from apps.backend.infrastructure.log_redaction import redact_sensitive_log_text

logger = logging.getLogger(__name__)

# Placeholder format (must match operator ``resolve_placeholders_deep``).
PLACEHOLDER_PREFIX = "[[agentlayer:secret:"
PLACEHOLDER_SUFFIX = "]]"


def _any_ingress_enabled() -> bool:
    return bool(getattr(_cfgmod, "CHAT_SECRET_HEURISTIC_REDACT_ENABLED", False)) or _vault.vault_available()


def _placeholder(token_id: uuid.UUID) -> str:
    return f"{PLACEHOLDER_PREFIX}{token_id}{PLACEHOLDER_SUFFIX}"


def heuristic_redact_text(s: str) -> tuple[str, int]:
    """Mask common secret patterns. Returns ``(new_text, number_of_subs_made)``."""
    if not getattr(_cfgmod, "CHAT_SECRET_HEURISTIC_REDACT_ENABLED", False):
        return s, 0
    if not s:
        return s, 0
    t = redact_sensitive_log_text(s)
    n = 0
    if t != s:
        n += 1
    rules: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\bsk-[a-zA-Z0-9]{10,}\b"), "[REDACTED:openai_sk]"),
        (re.compile(r"(?i)Bearer\s+[A-Za-z0-9._=\-+]{8,}"), "Bearer [REDACTED]"),
        (re.compile(r"(?i)\bxox[baprs]-[A-Za-z0-9-]{8,}\b"), "[REDACTED:slack_token]"),
        (re.compile(r"(?i)(api[_-]?key|client_secret)\s*[:=]\s*([^\s\"',\]}\n]+)"), r"\1=[REDACTED]"),
        (re.compile(r"(?i)(Authorization)\s*:\s*Bearer\s+[^\s\"',\n]+"), r"\1: Bearer [REDACTED]"),
        (re.compile(r"(?i)\bX-API-KEY\s*:\s*[^\s\"',\n]+"), "X-API-KEY: [REDACTED]"),
        (re.compile(r"(?i)(\"X-API-KEY\"\s*:\s*\")([^\"]{4,})(\")"), r"\1[REDACTED]\3"),
        (re.compile(r"(?i)appid=([A-Za-z0-9._-]+)"), "appid=[REDACTED]"),
    ]
    for pat, repl in rules:
        t2, k = pat.subn(repl, t)
        if k:
            n += k
            t = t2
    return t, n


def _json_sensitive_keys() -> frozenset[str]:
    return frozenset(x.lower() for x in ("discord_bot_token", "telegram_bot_token", "api_key"))


def _redact_json_obj(obj: Any, *, tenant_id: int, user_id: uuid.UUID) -> tuple[Any, int]:
    keys_lc = _json_sensitive_keys()
    n = 0

    def walk(o: Any) -> Any:
        nonlocal n
        if isinstance(o, dict):
            out: dict[str, Any] = {}
            for k, v in o.items():
                lk = str(k).lower()
                if lk in keys_lc and isinstance(v, str) and len(v.strip()) >= 4:
                    slot = (
                        "discord_bot_token"
                        if lk == "discord_bot_token"
                        else ("telegram_bot_token" if lk == "telegram_bot_token" else "api_key")
                    )
                    vid = _vault.vault_store(tenant_id=tenant_id, user_id=user_id, slot=slot, plaintext=v)
                    if vid is not None:
                        n += 1
                        out[k] = _placeholder(vid)
                        continue
                out[k] = walk(v)
            return out
        if isinstance(o, list):
            return [walk(x) for x in o]
        return o

    return walk(copy.deepcopy(obj)), n


def _vault_json_in_text(text: str, *, tenant_id: int, user_id: uuid.UUID | None) -> tuple[str, int]:
    if user_id is None or not _vault.vault_available():
        return text, 0
    st = text.strip()
    if not (st.startswith("{") or st.startswith("[")):
        return text, 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, 0
    new_obj, c = _redact_json_obj(parsed, tenant_id=tenant_id, user_id=user_id)
    if not c:
        return text, 0
    try:
        return json.dumps(new_obj, ensure_ascii=False), c
    except (TypeError, ValueError):
        return text, 0


def rewrite_user_text(text: str, *, tenant_id: int, user_id: uuid.UUID | None) -> tuple[str, int, int]:
    """Heuristic redact, then optional JSON→vault. Returns ``(text, heuristic_hits, vault_placeholders)``."""
    t, h = heuristic_redact_text(text)
    t2, v = _vault_json_in_text(t, tenant_id=tenant_id, user_id=user_id)
    return t2, h, v


def _rewrite_message_content(content: Any, *, tenant_id: int, user_id: uuid.UUID | None) -> tuple[Any, int, int]:
    if isinstance(content, str):
        t, h, v = rewrite_user_text(content, tenant_id=tenant_id, user_id=user_id)
        return t, h, v
    if isinstance(content, list):
        htot, vtot = 0, 0
        out: list[Any] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                nt, h, v = rewrite_user_text(part["text"], tenant_id=tenant_id, user_id=user_id)
                htot += h
                vtot += v
                p2 = dict(part)
                p2["text"] = nt
                out.append(p2)
            else:
                out.append(copy.deepcopy(part))
        return out, htot, vtot
    return content, 0, 0


def ingress_openai_messages_inplace(
    messages: list[dict[str, Any]],
    *,
    tenant_id: int,
    user_id: uuid.UUID | None,
) -> dict[str, Any]:
    """Mutate ``messages`` in place for ``role=user`` entries. Returns stats dict."""
    if not _any_ingress_enabled():
        return {"enabled": False, "redactions": 0, "vault_placeholders": 0}
    htot, vtot = 0, 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") != "user":
            continue
        new_c, h, v = _rewrite_message_content(m.get("content"), tenant_id=tenant_id, user_id=user_id)
        if h or v:
            m["content"] = new_c
            htot += h
            vtot += v
    if htot or vtot:
        logger.info(
            "chat_secret_ingress: user message scrub heuristic=%s vault_placeholders=%s",
            htot,
            vtot,
        )
    return {
        "enabled": True,
        "redactions": htot,
        "vault_placeholders": vtot,
    }


def ingress_messages_list_copy(
    messages: list[dict[str, Any]],
    *,
    tenant_id: int,
    user_id: uuid.UUID | None,
) -> list[dict[str, Any]]:
    """Deep-copy messages, run ingress on the copy, return the copy (for conversation DB writes)."""
    if not _any_ingress_enabled():
        return copy.deepcopy(messages)
    cloned = copy.deepcopy(messages)
    ingress_openai_messages_inplace(cloned, tenant_id=tenant_id, user_id=user_id)
    return cloned


def resolve_placeholders_deep(obj: Any, *, tenant_id: int, user_id: uuid.UUID) -> Any:
    """Recursively replace ``[[agentlayer:secret:<uuid>]]`` in strings with vault plaintext."""
    pat = re.compile(
        r"\[\[agentlayer:secret:([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\]\]",
    )

    def repl_str(s: str) -> str:
        out: list[str] = []
        last = 0
        for m in pat.finditer(s):
            out.append(s[last : m.start()])
            try:
                tid = uuid.UUID(m.group(1))
            except ValueError:
                out.append(m.group(0))
                last = m.end()
                continue
            pt = _vault.vault_get_plaintext(tid, tenant_id=tenant_id, user_id=user_id, consume=False)
            out.append(pt if pt is not None else m.group(0))
            last = m.end()
        out.append(s[last:])
        return "".join(out)

    if isinstance(obj, str):
        return repl_str(obj)
    if isinstance(obj, dict):
        return {k: resolve_placeholders_deep(v, tenant_id=tenant_id, user_id=user_id) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_placeholders_deep(x, tenant_id=tenant_id, user_id=user_id) for x in obj]
    if isinstance(obj, tuple):
        return tuple(resolve_placeholders_deep(x, tenant_id=tenant_id, user_id=user_id) for x in obj)
    return obj


def consume_placeholders_in_obj(obj: Any, *, tenant_id: int, user_id: uuid.UUID) -> None:
    """After successful apply, mark vault rows consumed for ids referenced in ``obj``."""
    if isinstance(obj, str):
        _vault.vault_consume_tokens_in_string(obj, tenant_id=tenant_id, user_id=user_id)
        return
    if isinstance(obj, dict):
        for v in obj.values():
            consume_placeholders_in_obj(v, tenant_id=tenant_id, user_id=user_id)
        return
    if isinstance(obj, list):
        for x in obj:
            consume_placeholders_in_obj(x, tenant_id=tenant_id, user_id=user_id)
