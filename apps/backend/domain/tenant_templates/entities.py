"""Tenant template definitions (Task 07)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TemplateDepartment:
    slug: str
    name: str


@dataclass(frozen=True)
class TemplateProfessionRole:
    slug: str
    name: str
    role_kind: str
    content_categories: tuple[str, ...]


@dataclass(frozen=True)
class TenantTemplate:
    id: str
    name: str
    description: str
    vertical_profile: str
    departments: tuple[TemplateDepartment, ...]
    profession_roles: tuple[TemplateProfessionRole, ...]
    workflow_defaults: dict[str, Any]
    seed_content_glob: str | None
    enabled_agent_ids: tuple[str, ...] = ()
    enabled_tool_domains: tuple[str, ...] = ()

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "vertical_profile": self.vertical_profile,
            "department_count": len(self.departments),
            "profession_role_count": len(self.profession_roles),
            "has_seed_content": bool(self.seed_content_glob),
            "workflow_defaults": dict(self.workflow_defaults),
            "enabled_agent_ids": list(self.enabled_agent_ids),
            "enabled_tool_domains": list(self.enabled_tool_domains),
        }
