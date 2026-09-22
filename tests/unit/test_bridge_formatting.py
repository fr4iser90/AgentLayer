"""Bridge presentation formatting: mention defanging, fence-aware chunking, Telegram HTML."""

from __future__ import annotations

import re

from apps.backend.domain.shared.bridge_formatting import (
    chunk_markdown,
    escape_html,
    markdown_to_html,
    neutralize_discord_mentions,
)

_TAG_RE = re.compile(r"<[^>]+>")


class TestNeutralizeDiscordMentions:
    def test_everyone_and_here_are_defanged(self) -> None:
        out = neutralize_discord_mentions("attention @everyone and @here look")
        assert "@everyone" not in out
        assert "@here" not in out
        assert "\u200b" in out
        # Still readable: only a zero-width space was inserted.
        assert out.replace("\u200b", "") == "attention @everyone and @here look"

    def test_case_insensitive(self) -> None:
        out = neutralize_discord_mentions("@EVERYONE @Here")
        assert "@EVERYONE" not in out
        assert "@Here" not in out

    def test_role_mention_defanged_but_id_kept(self) -> None:
        out = neutralize_discord_mentions("ping <@&123456789012345678>")
        assert "<@&123456789012345678>" not in out
        assert "123456789012345678" in out

    def test_word_containing_everyone_is_not_touched(self) -> None:
        # "@everyone" inside a longer token is not a ping; leave it alone.
        assert neutralize_discord_mentions("@everyoneElse") == "@everyoneElse"

    def test_empty_and_plain_text_pass_through(self) -> None:
        assert neutralize_discord_mentions("") == ""
        assert neutralize_discord_mentions("plain text") == "plain text"


class TestChunkMarkdown:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_markdown("hello", limit=100) == ["hello"]

    def test_empty_becomes_placeholder(self) -> None:
        assert chunk_markdown("   ", limit=100) == ["(empty reply)"]

    def test_every_chunk_respects_the_limit(self) -> None:
        text = "\n".join(f"line {i} " + "x" * 40 for i in range(60))
        for limit in (64, 200, 1900):
            for chunk in chunk_markdown(text, limit=limit):
                assert len(chunk) <= limit

    def test_splits_at_line_boundary_not_mid_word(self) -> None:
        lines = [f"line {i}: the quick brown fox" for i in range(20)]
        chunks = chunk_markdown("\n".join(lines), limit=80)
        assert len(chunks) > 1
        for chunk in chunks:
            for seg in chunk.split("\n"):
                assert seg in lines, f"chunked mid-line: {seg!r}"

    def test_open_fence_is_closed_in_the_chunk_that_ends_inside_it(self) -> None:
        body = "intro\n```python\n" + "\n".join(f"code_{i}" for i in range(40)) + "\n```\noutro"
        chunks = chunk_markdown(body, limit=120)
        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.count("```") % 2 == 0, f"unbalanced fence: {chunk!r}"

    def test_fence_content_survives_the_split(self) -> None:
        body = "```python\n" + "\n".join(f"code_{i}" for i in range(40)) + "\n```"
        joined = "\n".join(chunk_markdown(body, limit=120))
        for i in range(40):
            assert f"code_{i}" in joined

    def test_overlong_single_line_is_split_not_dropped(self) -> None:
        text = "y" * 500
        chunks = chunk_markdown(text, limit=100)
        assert "".join(chunks) == text
        assert all(len(c) <= 100 for c in chunks)

    def test_no_chunk_is_empty(self) -> None:
        text = "\n\n\n".join("word " * 50 for _ in range(5))
        assert all(c.strip() for c in chunk_markdown(text, limit=120))

    def test_tilde_fences_are_handled(self) -> None:
        body = "~~~\n" + "\n".join(f"t{i}" for i in range(40)) + "\n~~~"
        for chunk in chunk_markdown(body, limit=120):
            assert chunk.count("~~~") % 2 == 0

    def test_limit_holds_even_with_an_open_fence(self) -> None:
        # The reopened + closing marker must be paid for out of the limit, not on top.
        body = "```python\n" + "\n".join(f"code_{i}" for i in range(40)) + "\n```"
        for limit in (24, 40, 120):
            for chunk in chunk_markdown(body, limit=limit):
                assert len(chunk) <= limit, f"limit {limit}: {len(chunk)} {chunk!r}"


class TestEscapeHtml:
    def test_ampersand_lt_gt(self) -> None:
        assert escape_html('a & b < c > d') == "a &amp; b &lt; c &gt; d"

    def test_double_escaping_is_avoided_by_calling_once(self) -> None:
        assert escape_html("&lt;") == "&amp;lt;"


class TestMarkdownToHtml:
    def test_bold_and_italic(self) -> None:
        assert markdown_to_html("**bold**") == "<b>bold</b>"
        assert markdown_to_html("__bold__") == "<b>bold</b>"
        assert markdown_to_html("*it*") == "<i>it</i>"

    def test_inline_code(self) -> None:
        assert markdown_to_html("use `foo()` here") == 'use <code>foo()</code> here'

    def test_inline_code_contents_are_not_bolded(self) -> None:
        out = markdown_to_html("`**not bold**`")
        assert out == "<code>**not bold**</code>"

    def test_link(self) -> None:
        out = markdown_to_html("[docs](https://example.com/a)")
        assert out == '<a href="https://example.com/a">docs</a>'

    def test_heading_becomes_bold(self) -> None:
        assert markdown_to_html("## Title") == "<b>Title</b>"

    def test_html_in_source_is_escaped_not_injected(self) -> None:
        out = markdown_to_html("<script>alert(1)</script>")
        assert "<script>" not in out
        assert "&lt;script&gt;" in out

    def test_snake_case_is_not_rendered_italic(self) -> None:
        out = markdown_to_html("set mode_telegram and voice_reply now")
        assert "<i>" not in out
        assert "mode_telegram" in out

    def test_code_block_with_language(self) -> None:
        out = markdown_to_html("```python\nprint('hi')\n```")
        assert '<pre><code class="language-python">' in out
        assert "print('hi')" in out
        assert "</code></pre>" in out

    def test_code_block_html_is_escaped_inside(self) -> None:
        out = markdown_to_html("```\n<b>x</b>\n```")
        assert "<b>x</b>" not in out
        assert "&lt;b&gt;x&lt;/b&gt;" in out

    def test_junk_language_token_does_not_become_an_attribute(self) -> None:
        out = markdown_to_html('```"><script>\ncode\n```')
        assert 'class="language-"><script>"' not in out
        assert "<script>" not in out

    def test_output_is_balanced_for_telegram(self) -> None:
        src = (
            "# Titel\n\n**fett** und *kursiv* mit `code`.\n\n"
            "```python\nx = 1\n```\n\n"
            "Link: [hier](https://example.com)\n"
        )
        out = markdown_to_html(src)
        opens = re.findall(r"<(b|i|code|pre|a)\b", out)
        closes = re.findall(r"</(b|i|code|pre|a)>", out)
        assert sorted(opens) == sorted(closes)

    def test_empty(self) -> None:
        assert markdown_to_html("") == ""
