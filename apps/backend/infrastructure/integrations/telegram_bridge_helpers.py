"""Small pure helpers for the Telegram bridge adapter."""
from __future__ import annotations

from typing import Any


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    text = (text or "").strip() or "(empty reply)"
    out: list[str] = []
    while text:
        out.append(text[:limit])
        text = text[limit:]
    return out


def extract_reply(data: dict[str, Any]) -> str:
    err = data.get("error") or data.get("detail")
    if isinstance(err, dict):
        err = err.get("message") or str(err)
    if err and not data.get("choices"):
        return f"AgentLayer error: {err}"
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return f"Unexpected response: {data!r:.2000}"
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return f"(no text in response: {data!r:.1500})"


def normalize_bot_token(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) >= 2 and ((s[0] == s[-1] == '"') or (s[0] == s[-1] == "'")):
        s = s[1:-1].strip()
    return "".join(s.split())
