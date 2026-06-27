"""Collections use cases."""
from __future__ import annotations

from apps.backend.application.collections.commands import (
    EnsureCollectionCommand,
    PatchCollectionMetadataCommand,
)
from apps.backend.application.collections.dtos import CollectionDto
from apps.backend.application.collections.ports import CollectionRepository
from apps.backend.application.collections.queries import GetCollectionBySlugQuery, ListCollectionsQuery
from apps.backend.domain.collections.entities import Collection
from apps.backend.domain.collections.value_objects import CollectionSlug


def _to_dto(collection: Collection) -> CollectionDto:
    return CollectionDto(
        collection_id=collection.id,
        tenant_id=collection.tenant_id,
        owner_user_id=collection.owner_user_id,
        slug=collection.slug.value,
        title=collection.title,
        schema_hint=collection.schema_hint,
        metadata=dict(collection.metadata),
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def ensure_collection(repo: CollectionRepository, command: EnsureCollectionCommand) -> CollectionDto:
    collection = repo.ensure(
        tenant_id=command.tenant_id,
        owner_user_id=command.owner_user_id,
        slug=CollectionSlug.require(command.slug),
        title=command.title,
        schema_hint=command.schema_hint,
    )
    return _to_dto(collection)


def get_collection_by_slug(repo: CollectionRepository, query: GetCollectionBySlugQuery) -> CollectionDto | None:
    collection = repo.get_by_slug(query.owner_user_id, CollectionSlug.require(query.slug))
    return _to_dto(collection) if collection else None


def list_collections(repo: CollectionRepository, query: ListCollectionsQuery) -> list[CollectionDto]:
    return [_to_dto(item) for item in repo.list_for_owner(query.owner_user_id, limit=query.limit)]


def patch_collection_metadata(repo: CollectionRepository, command: PatchCollectionMetadataCommand) -> CollectionDto | None:
    collection = repo.patch_metadata(
        command.owner_user_id,
        CollectionSlug.require(command.slug),
        command.patch,
    )
    return _to_dto(collection) if collection else None
