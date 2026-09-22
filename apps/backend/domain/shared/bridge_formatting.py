"""Channel presentation for out-of-band bridges (Discord, Telegram).

``assistant_display.sanitize_assistant_display_text`` is content-level: it removes
reasoning leaks and tool JSON for *every* surface. This module is presentation-level:
it adapts already-clean markdown to what one specific chat protocol renders.

Pure functions, no I/O, no provider calls.
"""

from __future__ import annotations

import re

# Zero-width space: breaks Discord's literal "@everyone" match without changing what a
# human reads. Inserting it is the standard defang; removing the token entirely loses
# the fact that the model tried to ping.
_ZWSP = "\u200b"

# The trailing guard keeps a longer token ("@everyoneElse") alone: Discord only pings
# on the exact token, so rewriting the prefix of a longer word buys nothing.
_EVERYONE_RE = re.compile(r"@everyone(?![A-Za-z0-9_])", re.IGNORECASE)
_HERE_RE = re.compile(r"@here(?![A-Za-z0-9_])", re.IGNORECASE)
_ROLE_MENTION_RE = re.compile(r"<@&(\d+)>")

_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})")


def neutralize_discord_mentions(text: str) -> str:
    """Stop a model-authored mention from pinging a whole guild.

    ``@everyone``/``@here`` are the only mentions that reach users outside the
    conversation, so they are defanged textually rather than left to the library's
    ``AllowedMentions`` filter. Role pings (``<@&id>``) are defanged too and keep
    the id visible.
    """
    if not text:
        return text
    out = _EVERYONE_RE.sub(f"@{_ZWSP}everyone", text)
    out = _HERE_RE.sub(f"@{_ZWSP}here", out)
    out = _ROLE_MENTION_RE.sub(lambda m: f"<@{_ZWSP}&{m.group(1)}>", out)
    return out


def chunk_markdown(text: str, limit: int = 3500) -> list[str]:
    """Split markdown into <= ``limit``-char chunks with balanced code fences.

    A hard ``text[:limit]`` slice cuts words, URLs and --- worst --- code fences:
    every chunk past the first then renders as one runaway code block. Here we split
    on line boundaries, and a chunk that ends inside a fence closes it and the next
    one re-opens it.
    """
    body = (text or "").strip() or "(empty reply)"
    limit = max(16, int(limit))
    if len(body) <= limit:
        return [body]

    lines = _split_overlong_lines(body.split("\n"), limit)
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    fence: str | None = None

    def flush(keep_fence_open: bool) -> None:
        nonlocal buf, buf_len, fence
        rendered = "\n".join(buf)
        if fence and rendered.strip():
            rendered = f"{rendered}\n{fence}"
        if rendered.strip():
            chunks.append(rendered)
        if keep_fence_open and fence:
            buf = [fence]
            buf_len = len(fence) + 1
        else:
            buf = []
            buf_len = 0

    for line in lines:
        marker = _fence_marker(line)
        # An open fence must still fit its own closing marker inside the limit.
        room = limit - (len(fence) + 1 if fence else 0)
        if marker is not None:
            if fence is None:
                if buf_len + len(line) + 1 > room:
                    flush(keep_fence_open=False)
                fence = marker
            else:
                fence = None
            buf.append(line)
            buf_len += len(line) + 1
            continue

        if buf_len + len(line) + 1 > room:
            flush(keep_fence_open=fence is not None)
        buf.append(line)
        buf_len += len(line) + 1

    flush(keep_fence_open=False)
    return [c for c in chunks if c.strip()] or ["(empty reply)"]


def _fence_marker(line: str) -> str | None:
    m = _FENCE_RE.match(line)
    return m.group(1) if m else None


def _split_overlong_lines(lines: list[str], limit: int) -> list[str]:
    """Pre-split lines no chunk could ever hold, so the main loop only sees fits."""
    out: list[str] = []
    for line in lines:
        if len(line) <= limit:
            out.append(line)
            continue
        for i in range(0, len(line), limit):
            out.append(line[i : i + limit])
    return out


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def markdown_to_html(text: str) -> str:
    """Convert assistant markdown to the HTML subset Telegram's ``parse_mode=HTML`` accepts.

    Telegram has no markdown renderer unless you ask for one: without this, ``**bold**``
    and ``# heading`` arrive as literal asterisks and hashes. HTML is chosen over
    MarkdownV2 because MarkdownV2 requires escaping thirteen punctuation characters
    and any unescaped one fails the whole send.
    """
    if not text:
        return ""
    parts = re.split(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)", text)
    rendered: list[str] = []
    for part in parts:
        if part.startswith("```") or part.startswith("~~~"):
            rendered.append(_code_block_to_html(part))
        else:
            rendered.append(_inline_to_html(part))
    return "".join(rendered)


def _code_block_to_html(fence: str) -> str:
    inner = fence[3:-3]
    lang = ""
    code = inner
    if "\n" in inner:
        first, code = inner.split("\n", 1)
        lang = first.strip()
    # Only a sane language token may become a class attribute; anything else is dropped.
    cls = f' class="language-{lang}"' if lang and re.fullmatch(r"[A-Za-z0-9_+.#-]+", lang) else ""
    return f"<pre><code{cls}>{escape_html(code.strip(chr(10)))}</code></pre>"


def _inline_to_html(s: str) -> str:
    protected: list[str] = []

    def keep(fragment: str) -> str:
        protected.append(fragment)
        return f"\x00{len(protected) - 1}\x00"

    s = escape_html(s)
    # Inline code is protected first so its contents are never bolded or linked.
    s = re.sub(r"`([^`\n]+)`", lambda m: keep(f"<code>{m.group(1)}</code>"), s)
    s = re.sub(
        r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
        lambda m: keep(f'<a href="{m.group(2)}">{m.group(1)}</a>'),
        s,
    )
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+?)\*(?!\*)", r"<i>\1</i>", s)
    # The word guards keep snake_case (``mode_telegram``) from rendering italic.
    s = re.sub(r"(?<!\w)_(?!\s)([^_\n]+?)(?<!\s)_(?!\w)", r"<i>\1</i>", s)
    s = re.sub(r"(?m)^#{1,6}[ \t]*(.+)$", r"<b>\1</b>", s)

    for i, fragment in enumerate(protected):
        s = s.replace(f"\x00{i}\x00", fragment)
    return s
