"""Repository ports for setup profiles."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.setup.entities import SetupProfile
from apps.backend.domain.setup.value_objects import SetupProfileName


class SetupProfileRepository(Protocol):
    def get(self, name: SetupProfileName) -> SetupProfile | None: ...

    def list_profiles(self) -> list[SetupProfile]: ...

    def save(self, profile: SetupProfile) -> SetupProfile: ...
