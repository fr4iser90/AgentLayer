"""Telegram audio-file intake: file vs document classification, mime resolution,
and the filename the STT upload actually carries."""

from __future__ import annotations

import datetime

import pytest
from telegram import Audio, Chat, Document, Message, Update, User
from telegram.ext import filters

from apps.backend.domain.voice import stt
from apps.backend.infrastructure.integrations.telegram_bridge_helpers import (
    audio_document,
    audio_mime,
    select_audio_payload,
)


def _update(**msg_kwargs: object) -> Update:
    base = {
        "message_id": 1,
        "date": datetime.datetime.now(datetime.timezone.utc),
        "chat": Chat(id=1, type="private"),
        "from_user": User(id=2, is_bot=False, first_name="x"),
    }
    base.update(msg_kwargs)
    return Update(update_id=1, message=Message(**base))


class _Payload:
    def __init__(self, mime_type: str = "", file_name: str = "") -> None:
        self.mime_type = mime_type
        self.file_name = file_name


class TestAudioDocument:
    def test_mp3_mislabelled_as_octet_stream_is_still_audio_by_extension(self) -> None:
        assert audio_document(_Payload("application/octet-stream", "Song.MP3")) == "audio/mpeg"

    def test_explicit_audio_mime_wins(self) -> None:
        assert audio_document(_Payload("audio/flac", "track")) == "audio/flac"

    def test_mime_parameters_are_stripped(self) -> None:
        assert audio_document(_Payload("audio/mpeg; codecs=mpeg4", "x")) == "audio/mpeg"

    def test_pdf_is_not_audio(self) -> None:
        assert audio_document(_Payload("application/pdf", "plan.pdf")) is None

    def test_image_document_is_not_audio(self) -> None:
        assert audio_document(_Payload("image/png", "p.png")) is None

    def test_extensionless_unknown_mime_is_not_audio(self) -> None:
        assert audio_document(_Payload("application/octet-stream", "blob")) is None

    def test_none_is_not_audio(self) -> None:
        assert audio_document(None) is None

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("a.mp3", "audio/mpeg"),
            ("a.m4a", "audio/mp4"),
            ("a.aac", "audio/aac"),
            ("a.wav", "audio/wav"),
            ("a.ogg", "audio/ogg"),
            ("a.opus", "audio/opus"),
            ("a.flac", "audio/flac"),
            ("a.webm", "audio/webm"),
            ("a.amr", "audio/amr"),
        ],
    )
    def test_extensions_map(self, name: str, expected: str) -> None:
        assert audio_document(_Payload("application/octet-stream", name)) == expected


class TestAudioMime:
    def test_mime_wins_over_extension(self) -> None:
        assert audio_mime(_Payload("audio/mp4", "lies.mp3")) == "audio/mp4"

    def test_extension_fallback_when_mime_missing(self) -> None:
        assert audio_mime(_Payload("", "track.flac")) == "audio/flac"

    def test_unknown_falls_back_to_default(self) -> None:
        assert audio_mime(_Payload("", "weird")) == "audio/ogg"
        assert audio_mime(_Payload("application/zip", "weird.zip")) == "audio/ogg"

    def test_custom_default(self) -> None:
        assert audio_mime(_Payload("", "x"), default="audio/webm") == "audio/webm"


class TestSttUploadFilename:
    """The upload filename is how many STT backends sniff the format, so an unmapped
    mime silently becomes ``audio.audio``."""

    @pytest.mark.parametrize(
        "mime,expected",
        [
            ("audio/ogg", "audio.ogg"),
            ("audio/opus", "audio.ogg"),
            ("audio/mpeg", "audio.mp3"),
            ("audio/mp4", "audio.m4a"),
            ("audio/webm", "audio.webm"),
            ("audio/wav", "audio.wav"),
            ("audio/x-wav", "audio.wav"),
            ("audio/aac", "audio.aac"),
            ("audio/amr", "audio.amr"),
            ("audio/aiff", "audio.aiff"),
            ("audio/flac", "audio.flac"),
        ],
    )
    def test_supported_mimes_get_a_real_extension(self, mime: str, expected: str) -> None:
        assert stt._guess_filename(mime) == expected

    def test_mime_parameters_are_stripped(self) -> None:
        assert stt._guess_filename("audio/mpeg; codecs=x") == "audio.mp3"

    def test_unknown_mime_is_marked_not_silently_wrong(self) -> None:
        assert stt._guess_filename("application/octet-stream") == "audio.audio"


class TestFilterRouting:
    """The bridge registers VOICE before AUDIO|Document.ALL and PTB runs only the
    first matching handler, so the filters must be disjoint or a voice note would
    be transcribed twice."""

    AUDIO_FILTER = filters.AUDIO | filters.Document.ALL

    def test_audio_goes_to_the_audio_handler_not_voice(self) -> None:
        u = _update(
            audio=Audio(
                file_id="af",
                file_unique_id="au",
                duration=3,
                mime_type="audio/mpeg",
                file_name="s.mp3",
            )
        )
        assert not filters.VOICE.check_update(u)
        assert self.AUDIO_FILTER.check_update(u)

    def test_voice_note_is_not_double_handled(self) -> None:
        from telegram import Voice

        u = _update(voice=Voice(file_id="vf", file_unique_id="vu", duration=3, mime_type="audio/ogg"))
        assert filters.VOICE.check_update(u)
        assert not self.AUDIO_FILTER.check_update(u), "voice would be transcribed twice"

    def test_audio_document_reaches_the_audio_handler(self) -> None:
        u = _update(
            document=Document(
                file_id="gf",
                file_unique_id="gu",
                mime_type="application/octet-stream",
                file_name="song.mp3",
            )
        )
        assert self.AUDIO_FILTER.check_update(u)
        # ...and the classifier agrees it is audio, so it is not silently dropped.
        assert audio_document(u.message.document) == "audio/mpeg"

    def test_pdf_document_reaches_the_handler_but_is_classified_away(self) -> None:
        u = _update(
            document=Document(
                file_id="df", file_unique_id="du", mime_type="application/pdf", file_name="p.pdf"
            )
        )
        assert self.AUDIO_FILTER.check_update(u)
        assert audio_document(u.message.document) is None

    def test_plain_text_matches_neither(self) -> None:
        u = _update(text="hallo")
        assert not filters.VOICE.check_update(u)
        assert not self.AUDIO_FILTER.check_update(u)


class TestSelectAudioPayload:
    """The handler needs the payload *object* (for ``file_id``) and its mime as a
    pair. Resolving them separately is how an audio document gets mis-handled."""

    def test_audio_object_is_returned_with_its_mime(self) -> None:
        u = _update(
            audio=Audio(
                file_id="af",
                file_unique_id="au",
                duration=3,
                mime_type="audio/mpeg",
                file_name="s.mp3",
            )
        )
        payload, mime = select_audio_payload(u.message)
        assert payload is u.message.audio
        assert payload.file_id == "af"
        assert mime == "audio/mpeg"

    def test_document_payload_is_the_document_object_not_a_mime_string(self) -> None:
        u = _update(
            document=Document(
                file_id="gf",
                file_unique_id="gu",
                mime_type="application/octet-stream",
                file_name="song.mp3",
            )
        )
        payload, mime = select_audio_payload(u.message)
        assert payload is u.message.document
        assert payload.file_id == "gf", "handler must get the object, not the mime string"
        assert mime == "audio/mpeg"

    def test_non_audio_document_selects_nothing(self) -> None:
        u = _update(
            document=Document(
                file_id="df", file_unique_id="du", mime_type="application/pdf", file_name="p.pdf"
            )
        )
        assert select_audio_payload(u.message) is None

    def test_text_message_selects_nothing(self) -> None:
        assert select_audio_payload(_update(text="hallo").message) is None

    def test_none_message_selects_nothing(self) -> None:
        assert select_audio_payload(None) is None

    def test_audio_wins_over_a_document_on_the_same_message(self) -> None:
        u = _update(
            audio=Audio(
                file_id="af",
                file_unique_id="au",
                duration=3,
                mime_type="audio/ogg",
                file_name="note.ogg",
            ),
            document=Document(
                file_id="df", file_unique_id="du", mime_type="application/pdf", file_name="p.pdf"
            ),
        )
        payload, mime = select_audio_payload(u.message)
        assert payload is u.message.audio
        assert mime == "audio/ogg"
