"""Plugin system entities."""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.backend.domain.plugin_system.value_objects import PluginId


@dataclass(frozen=True, slots=True)
class PluginCapability:
    name: str
    risk: str = "normal"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("plugin capability name must not be blank")


@dataclass(slots=True)
class PluginManifest:
    id: PluginId
    label: str
    capabilities: list[PluginCapability] = field(default_factory=list)
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("plugin label must not be blank")
