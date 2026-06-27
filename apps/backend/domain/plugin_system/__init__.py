"""Plugin system bounded context."""
from apps.backend.domain.plugin_system.entities import PluginCapability, PluginManifest
from apps.backend.domain.plugin_system.repositories import PluginManifestRepository
from apps.backend.domain.plugin_system.value_objects import PluginId

__all__ = [
    "PluginCapability",
    "PluginId",
    "PluginManifest",
    "PluginManifestRepository",
]
