"""Setup use cases."""
from __future__ import annotations

from apps.backend.application.setup.commands import SaveSetupProfileCommand
from apps.backend.application.setup.dtos import SetupProfileDto, SetupStepDto
from apps.backend.application.setup.ports import SetupProfileRepository
from apps.backend.application.setup.queries import GetSetupProfileQuery, ListSetupProfilesQuery
from apps.backend.domain.setup.entities import SetupProfile, SetupStep
from apps.backend.domain.setup.schemas import validate_setup_completed, validate_setup_step_title
from apps.backend.domain.setup.value_objects import SetupProfileName, SetupStepKey


def _to_dto(profile: SetupProfile) -> SetupProfileDto:
    steps = [
        SetupStepDto(key=step.key.value, title=step.title, completed=step.completed)
        for step in profile.steps
    ]
    return SetupProfileDto(name=profile.name.value, steps=steps, completion_ratio=profile.completion_ratio())


def get_setup_profile(repo: SetupProfileRepository, query: GetSetupProfileQuery) -> SetupProfileDto | None:
    profile = repo.get(SetupProfileName.parse(query.name))
    return _to_dto(profile) if profile else None


def list_setup_profiles(repo: SetupProfileRepository, query: ListSetupProfilesQuery) -> list[SetupProfileDto]:
    _ = query
    return [_to_dto(item) for item in repo.list_profiles()]


def save_setup_profile(repo: SetupProfileRepository, command: SaveSetupProfileCommand) -> SetupProfileDto:
    profile = SetupProfile(
        name=SetupProfileName.parse(command.name),
        steps=[
            SetupStep(
                key=SetupStepKey.parse(item.key),
                title=validate_setup_step_title(item.title),
                completed=validate_setup_completed(item.completed),
            )
            for item in command.steps
        ],
    )
    return _to_dto(repo.save(profile))
