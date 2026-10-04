"""Identity use cases."""
from __future__ import annotations

from apps.backend.application.identity.dtos import TenantDto, UserDto
from apps.backend.application.identity.queries import GetTenantQuery, GetUserByEmailQuery, GetUserQuery
from apps.backend.domain.identity.entities import Tenant, User
from apps.backend.domain.identity.repositories import TenantRepository, UserRepository
from apps.backend.domain.identity.schemas import validate_email, validate_tenant_id


def _user_to_dto(user: User) -> UserDto:
    return UserDto(
        id=user.id,
        tenant_id=int(user.tenant_id),
        email=str(user.email),
        role=user.role,
    )


def _tenant_to_dto(tenant: Tenant) -> TenantDto:
    return TenantDto(id=int(tenant.id), name=tenant.name)


def get_user(repo: UserRepository, query: GetUserQuery) -> UserDto | None:
    user = repo.get_by_id(query.user_id)
    return _user_to_dto(user) if user is not None else None


def get_user_by_email(repo: UserRepository, query: GetUserByEmailQuery) -> UserDto | None:
    user = repo.get_by_email(validate_email(query.email))
    return _user_to_dto(user) if user is not None else None


def get_tenant(repo: TenantRepository, query: GetTenantQuery) -> TenantDto | None:
    tenant = repo.get(validate_tenant_id(query.tenant_id))
    return _tenant_to_dto(tenant) if tenant is not None else None
