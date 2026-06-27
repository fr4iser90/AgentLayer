"""Agent runtime use cases."""
from __future__ import annotations

from apps.backend.application.agent_runtime.commands import AppendAgentTurnCommand, SaveAgentRunCommand
from apps.backend.application.agent_runtime.dtos import AgentRunDto
from apps.backend.application.agent_runtime.ports import AgentRunRepository
from apps.backend.application.agent_runtime.queries import GetAgentRunQuery
from apps.backend.domain.agent_runtime.entities import AgentRun, AgentTurn
from apps.backend.domain.agent_runtime.schemas import validate_agent_run_status, validate_agent_turn_role
from apps.backend.domain.agent_runtime.value_objects import AgentId, AgentRunId


def _to_dto(run: AgentRun) -> AgentRunDto:
    return AgentRunDto(
        run_id=run.id.value,
        agent_id=run.agent_id.value,
        status=run.status,
        user_id=run.user_id,
        transcript=list(run.transcript),
    )


def get_agent_run(repo: AgentRunRepository, query: GetAgentRunQuery) -> AgentRunDto | None:
    run = repo.get(AgentRunId.parse(query.run_id))
    return _to_dto(run) if run else None


def save_agent_run(repo: AgentRunRepository, command: SaveAgentRunCommand) -> AgentRunDto:
    run = AgentRun(
        id=AgentRunId.parse(command.run_id),
        agent_id=AgentId.parse(command.agent_id),
        status=validate_agent_run_status(command.status),
        user_id=command.user_id,
        transcript=list(command.transcript),
    )
    return _to_dto(repo.save(run))


def append_agent_turn(repo: AgentRunRepository, command: AppendAgentTurnCommand) -> None:
    turn = AgentTurn(
        run_id=AgentRunId.parse(command.run_id),
        role=validate_agent_turn_role(command.role),
        content=command.content,
    )
    repo.append_turn(turn)
