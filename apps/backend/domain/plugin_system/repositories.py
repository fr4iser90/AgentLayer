"""Repository ports for plugin manifests."""
from __future__ import annotations

from typing import Protocol

from apps.backend.domain.plugin_system.entities import PluginManifest
from apps.backend.domain.plugin_system.value_objects import PluginId


class PluginManifestRepository(Protocol):
    def get(self, plugin_id: PluginId) -> PluginManifest | None: ...

    def list_enabled(self) -> list[PluginManifest]: ...

    def save(self, manifest: PluginManifest) -> PluginManifest: ...
