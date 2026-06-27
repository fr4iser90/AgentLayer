"""Studio use cases."""
from __future__ import annotations

from apps.backend.application.studio.commands import SaveStudioJobCommand
from apps.backend.application.studio.dtos import StudioJobDto
from apps.backend.application.studio.ports import StudioJobRepository
from apps.backend.application.studio.queries import GetStudioJobQuery, ListStudioJobsQuery
from apps.backend.domain.studio.entities import StudioJob
from apps.backend.domain.studio.schemas import validate_studio_job_status, validate_studio_payload
from apps.backend.domain.studio.value_objects import StudioJobId, StudioJobKind


def _to_dto(job: StudioJob) -> StudioJobDto:
    return StudioJobDto(
        job_id=job.id.value,
        kind=job.kind.value,
        status=job.status,
        payload=dict(job.payload),
    )


def get_studio_job(repo: StudioJobRepository, query: GetStudioJobQuery) -> StudioJobDto | None:
    job = repo.get(StudioJobId.parse(query.job_id))
    return _to_dto(job) if job else None


def list_studio_jobs(repo: StudioJobRepository, query: ListStudioJobsQuery) -> list[StudioJobDto]:
    status = validate_studio_job_status(query.status) if query.status else None
    return [_to_dto(item) for item in repo.list_by_status(status)]


def save_studio_job(repo: StudioJobRepository, command: SaveStudioJobCommand) -> StudioJobDto:
    job = StudioJob(
        id=StudioJobId.parse(command.job_id),
        kind=StudioJobKind.parse(command.kind),
        status=validate_studio_job_status(command.status),
        payload=validate_studio_payload(command.payload),
    )
    return _to_dto(repo.save(job))
