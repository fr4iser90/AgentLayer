"""Sharing use cases."""
from __future__ import annotations

from apps.backend.application.sharing.commands import SaveShareGrantCommand
from apps.backend.application.sharing.dtos import ShareGrantDto
from apps.backend.application.sharing.ports import ShareGrantRepository
from apps.backend.application.sharing.queries import GetShareGrantQuery, ListShareGrantsQuery
from apps.backend.domain.shares.entities import ShareGrant
from apps.backend.domain.shares.schemas import validate_grantee, validate_share_role
from apps.backend.domain.shares.value_objects import ShareId, ShareResource


def _to_dto(grant: ShareGrant) -> ShareGrantDto:
    return ShareGrantDto(
        share_id=grant.id.value,
        resource_kind=grant.resource.kind,
        resource_id=grant.resource.resource_id,
        grantee=grant.grantee,
        role=grant.role,
        revoked=grant.revoked,
    )


def get_share_grant(repo: ShareGrantRepository, query: GetShareGrantQuery) -> ShareGrantDto | None:
    grant = repo.get(ShareId.parse(query.share_id))
    return _to_dto(grant) if grant else None


def list_share_grants(repo: ShareGrantRepository, query: ListShareGrantsQuery) -> list[ShareGrantDto]:
    resource = ShareResource(kind=query.resource_kind, resource_id=query.resource_id)
    return [_to_dto(item) for item in repo.list_for_resource(resource)]


def save_share_grant(repo: ShareGrantRepository, command: SaveShareGrantCommand) -> ShareGrantDto:
    grant = ShareGrant(
        id=ShareId.parse(command.share_id),
        resource=ShareResource(kind=command.resource_kind, resource_id=command.resource_id),
        grantee=validate_grantee(command.grantee),
        role=validate_share_role(command.role),
        revoked=command.revoked,
    )
    return _to_dto(repo.save(grant))
