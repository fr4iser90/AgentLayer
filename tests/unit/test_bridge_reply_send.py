"""Bridge send paths: HTML parse_mode on Telegram, mention defanging on Discord,
and that a text-triggered turn honours the user's voice-reply preference."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from apps.backend.domain.voice import bridge_reply, voice_policy


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def _log(self, name: str, **kw: object) -> None:
        self.calls.append((name, kw))

    def texts(self, name: str) -> list[dict]:
        return [kw for n, kw in self.calls if n == name]


class _FakeTelegramMsg(_Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.message_id = 1

    async def reply_text(self, text: str, **kw: object) -> None:
        self._log("reply_text", text=text, **kw)

    async def reply_audio(self, **kw: object) -> None:
        self._log("reply_audio", **kw)


class _FakeBot(_Recorder):
    async def send_message(self, **kw: object) -> None:
        self._log("send_message", **kw)


class _FakeContext:
    def __init__(self) -> None:
        self.bot = _FakeBot()


class _FakeChat:
    def __init__(self) -> None:
        self.id = 555


class _FakeChannel(_Recorder):
    async def send(self, content: str = "", **kw: object) -> None:
        self._log("channel_send", content=content, **kw)


class _FakeDiscordMessage(_Recorder):
    def __init__(self) -> None:
        super().__init__()
        self.channel = _FakeChannel()

    async def reply(self, content: str = "", **kw: object) -> None:
        self._log("reply", content=content, **kw)


def _prefs(monkeypatch: pytest.MonkeyPatch, **over: object) -> uuid.UUID:
    monkeypatch.setattr(voice_policy, "operator_voice_row", lambda: {"voice_enabled": True})
    base = {
        "input_enabled": True,
        "output_enabled": False,
        "language": "de",
        "voice_id": None,
        "mode_web": "push_to_talk",
        "mode_telegram": "text_only",
        "mode_discord": "text_only",
        "edit_transcript_before_send": True,
    }
    base.update(over)
    uid = uuid.uuid4()
    monkeypatch.setattr(voice_policy, "user_voice_prefs_get", lambda _u: dict(base))
    return uid


def _send_tg(uid: uuid.UUID, text: str) -> tuple[_FakeTelegramMsg, _FakeContext]:
    msg, ctx = _FakeTelegramMsg(), _FakeContext()
    asyncio.run(
        bridge_reply.send_telegram_agent_reply(
            msg=msg,
            context=ctx,
            chat=_FakeChat(),
            thread_kw={},
            user_id=uid,
            reply_text=text,
        )
    )
    return msg, ctx


def _send_dc(uid: uuid.UUID, text: str) -> _FakeDiscordMessage:
    message = _FakeDiscordMessage()
    asyncio.run(
        bridge_reply.send_discord_agent_reply(
            message=message, user_id=uid, reply_text=text
        )
    )
    return message


class TestTelegramSend:
    def test_text_is_sent_with_html_parse_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch)
        msg, ctx = _send_tg(uid, "**wichtig**")
        for kw in msg.texts("reply_text") + ctx.bot.texts("send_message"):
            assert kw.get("parse_mode") == "HTML"

    def test_markdown_is_rendered_not_literal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch)
        msg, _ = _send_tg(uid, "# Titel\n\n**fett** und `code`")
        sent = msg.texts("reply_text")[0]["text"]
        assert "<b>Titel</b>" in sent
        assert "<b>fett</b>" in sent
        assert "<code>code</code>" in sent
        assert "**fett**" not in sent

    def test_continuation_chunks_also_get_parse_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch)
        long_md = "\n\n".join(f"**block {i}** with `code`" for i in range(400))
        msg, ctx = _send_tg(uid, long_md)
        extra = ctx.bot.texts("send_message")
        assert len(extra) >= 1, "expected the reply to overflow into continuation sends"
        for kw in extra:
            assert kw.get("parse_mode") == "HTML"

    def test_no_voice_when_output_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch, mode_telegram="text_only", output_enabled=False)
        msg, _ = _send_tg(uid, "hallo")
        assert msg.texts("reply_audio") == []

    def test_voice_reply_mode_sends_audio_and_no_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch, mode_telegram="voice_reply", output_enabled=True)
        monkeypatch.setattr(
            bridge_reply, "synthesize_for_bridge", _fake_tts(b"RIFFfake", "audio/wav")
        )
        msg, ctx = _send_tg(uid, "hallo")
        assert len(msg.texts("reply_audio")) == 1
        assert msg.texts("reply_text") == []
        assert ctx.bot.texts("send_message") == []

    def test_audio_filename_matches_the_bytes_not_the_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        uid = _prefs(monkeypatch, mode_telegram="voice_both", output_enabled=True)
        monkeypatch.setattr(
            bridge_reply, "synthesize_for_bridge", _fake_tts(b"RIFFfake", "audio/wav")
        )
        msg, _ = _send_tg(uid, "hallo")
        infile = msg.texts("reply_audio")[0]["audio"]
        assert infile.filename == "agent.wav"

    def test_text_still_sent_when_tts_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch, mode_telegram="voice_reply", output_enabled=True)

        async def no_audio(*_a: object, **_k: object) -> None:
            return None

        monkeypatch.setattr(bridge_reply, "synthesize_for_bridge", no_audio)
        msg, _ = _send_tg(uid, "hallo")
        assert msg.texts("reply_audio") == []
        assert len(msg.texts("reply_text")) == 1, "TTS failure must not swallow the answer"


class TestDiscordSend:
    def test_everyone_is_defanged_before_sending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch)
        message = _send_dc(uid, "Achtung @everyone hier lang")
        sent = message.texts("reply")[0]["content"]
        assert "@everyone" not in sent
        assert "\u200b" in sent

    def test_markdown_is_left_for_discord_native_renderer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        uid = _prefs(monkeypatch)
        message = _send_dc(uid, "**fett**")
        assert "**fett**" in message.texts("reply")[0]["content"]

    def test_voice_reply_mode_sends_audio_and_no_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch, mode_discord="voice_reply", output_enabled=True)
        monkeypatch.setattr(
            bridge_reply, "synthesize_for_bridge", _fake_tts(b"ID3fake", "audio/mpeg")
        )
        message = _send_dc(uid, "hallo")
        assert len(message.channel.texts("channel_send")) == 1
        assert message.texts("reply") == []

    def test_both_mode_sends_audio_and_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        uid = _prefs(monkeypatch, mode_discord="voice_both", output_enabled=True)
        monkeypatch.setattr(
            bridge_reply, "synthesize_for_bridge", _fake_tts(b"ID3fake", "audio/mpeg")
        )
        message = _send_dc(uid, "hallo")
        # Audio rides channel.send(file=...), the text leg rides reply().
        assert len(message.channel.texts("channel_send")) == 1
        assert message.channel.texts("channel_send")[0].get("file") is not None
        assert len(message.texts("reply")) == 1
        assert message.texts("reply")[0]["content"] == "hallo"


def _fake_tts(payload: bytes, mime: str):
    async def _synth(_user: object, _text: str, *, channel: str = "") -> tuple[bytes, str]:
        return payload, mime

    return _synth


class TestAudioFilename:
    @pytest.mark.parametrize(
        "mime,expected",
        [
            ("audio/wav", "agent.wav"),
            ("audio/x-wav", "agent.wav"),
            ("audio/mpeg", "agent.mp3"),
            ("audio/ogg", "agent.ogg"),
            ("audio/mp4", "agent.m4a"),
            ("audio/wav; codecs=1", "agent.wav"),
            ("", "agent.mp3"),
            ("application/octet-stream", "agent.mp3"),
        ],
    )
    def test_extension_follows_mime(self, mime: str, expected: str) -> None:
        assert bridge_reply._audio_filename(mime) == expected
