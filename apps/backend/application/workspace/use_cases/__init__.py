"""Workspace use cases."""
from __future__ import annotations

from apps.backend.application.workspace.commands import SaveWorkspaceCommand
from apps.backend.application.workspace.dtos import WorkspaceDto
from apps.backend.application.workspace.ports import WorkspaceRepository
from apps.backend.application.workspace.queries import GetWorkspaceQuery, ListWorkspacesQuery
from apps.backend.domain.workspace.entities import Workspace
from apps.backend.domain.workspace.schemas import validate_verify_command, validate_workspace_path
from apps.backend.domain.workspace.value_objects import WorkspaceId, WorkspaceName


def _to_dto(workspace: Workspace) -> WorkspaceDto:
    return WorkspaceDto(
        workspace_id=workspace.id.value,
        tenant_id=workspace.tenant_id,
        owner_user_id=workspace.owner_user_id,
        name=workspace.name.value,
        path=workspace.path,
        verify_required=workspace.verify_required,
        verify_command=workspace.verify_command,
    )


def get_workspace(repo: WorkspaceRepository, query: GetWorkspaceQuery) -> WorkspaceDto | None:
    workspace = repo.get(WorkspaceId.parse(query.workspace_id), user_id=query.user_id)
    return _to_dto(workspace) if workspace else None


def list_workspaces(repo: WorkspaceRepository, query: ListWorkspacesQuery) -> list[WorkspaceDto]:
    return [_to_dto(item) for item in repo.list_for_user(query.user_id, limit=query.limit)]


def save_workspace(repo: WorkspaceRepository, command: SaveWorkspaceCommand) -> WorkspaceDto:
    workspace = Workspace(
        id=WorkspaceId.parse(command.workspace_id),
        tenant_id=command.tenant_id,
        owner_user_id=command.owner_user_id,
        name=WorkspaceName.parse(command.name),
        path=validate_workspace_path(command.path),
        verify_required=command.verify_required,
        verify_command=validate_verify_command(command.verify_command),
    )
    return _to_dto(repo.save(workspace))
