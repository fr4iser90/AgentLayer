"""Voice use cases."""
from __future__ import annotations

from apps.backend.application.voice.commands import PrepareSpeechCommand, SaveVoiceProfileCommand
from apps.backend.application.voice.dtos import SpeechRequestDto, VoiceProfileDto
from apps.backend.application.voice.ports import VoiceProfileRepository
from apps.backend.application.voice.queries import GetVoiceProfileQuery, ListVoiceProfilesQuery
from apps.backend.domain.voice.entities import SpeechRequest, VoiceProfile
from apps.backend.domain.voice.schemas import validate_language_tag, validate_speech_text
from apps.backend.domain.voice.value_objects import VoiceId, VoiceProvider


def _to_dto(profile: VoiceProfile) -> VoiceProfileDto:
    return VoiceProfileDto(
        voice_id=profile.id.value,
        provider=profile.provider.value,
        display_name=profile.display_name,
        language=profile.language,
        enabled=profile.enabled,
    )


def get_voice_profile(repo: VoiceProfileRepository, query: GetVoiceProfileQuery) -> VoiceProfileDto | None:
    profile = repo.get(VoiceId.parse(query.voice_id))
    return _to_dto(profile) if profile else None


def list_voice_profiles(repo: VoiceProfileRepository, query: ListVoiceProfilesQuery) -> list[VoiceProfileDto]:
    provider = VoiceProvider.parse(query.provider) if query.provider else None
    return [_to_dto(item) for item in repo.list_by_provider(provider)]


def save_voice_profile(repo: VoiceProfileRepository, command: SaveVoiceProfileCommand) -> VoiceProfileDto:
    profile = VoiceProfile(
        id=VoiceId.parse(command.voice_id),
        provider=VoiceProvider.parse(command.provider),
        display_name=command.display_name,
        language=validate_language_tag(command.language),
        enabled=command.enabled,
    )
    return _to_dto(repo.save(profile))


def prepare_speech(command: PrepareSpeechCommand) -> SpeechRequestDto:
    request = SpeechRequest(voice_id=VoiceId.parse(command.voice_id), text=validate_speech_text(command.text))
    return SpeechRequestDto(voice_id=request.voice_id.value, text=request.text)
