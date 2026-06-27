"""Infrastructure adapter for speech-prep LLM summaries."""

from __future__ import annotations

from typing import Any

from apps.backend.domain.voice import speech_prep as domain
from apps.backend.infrastructure.catalog_llm_client import post_catalog_chat_completions


class _SpeechPrepDeps:
    @staticmethod
    def post_catalog_chat_completions(**kwargs: Any) -> tuple[dict[str, Any], Any]:
        return post_catalog_chat_completions(**kwargs)


domain.register_speech_prep_dependencies(_SpeechPrepDeps())

needs_speech_summary = domain.needs_speech_summary
prepare_speech_text = domain.prepare_speech_text
strip_emoji_text = domain.strip_emoji_text
strip_text_for_speech = domain.strip_text_for_speech
summarize_for_speech = domain.summarize_for_speech
